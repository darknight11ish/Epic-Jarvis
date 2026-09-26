/**
 * The Markdown renderer: a compact, dependency-free one, shared by the
 * quickbar (main.js - the streamed answer and the approval preview) and the
 * Brain's deep questions (deep.js).
 *
 * Everything is HTML-escaped before any markup is introduced, so model
 * output can never inject nodes, and only http(s) links are made into
 * links. `scripts/markdown-test.mjs` runs it.
 *
 * Moved out of main.js unchanged so a second window can use the same one
 * rather than a copy that drifts.
 *
 * @module markdown
 */

/* ==========================================================================
   Markdown
   --------------------------------------------------------------------------
   A compact, dependency-free renderer. The content security policy forbids
   remote scripts, and a streaming card only needs the commonmark subset a chat
   model actually emits. Everything is HTML-escaped before any markup is
   introduced, so model output can never inject nodes.
   ========================================================================== */

export function escapeHtml(text) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/** Inline spans: code, bold, italic, strikethrough, links. */
function renderInline(text) {
  let out = escapeHtml(text);

  // Placeholders carry a per-call nonce. A fixed `@@JARVISCODE0@@` was
  // predictable, so model output containing that literal string was
  // substituted with an unrelated code span — or with `<code>undefined</code>`
  // when the index did not exist. Not an escape, but not what the model wrote.
  const nonce = Math.random().toString(36).slice(2, 10);

  // Inline code is lifted out first so its contents survive the emphasis
  // passes untouched, then restored at the end.
  const codeSpans = [];
  out = out.replace(/`([^`\n]+)`/g, (_match, code) => {
    codeSpans.push(code);
    return `@@C${nonce}${codeSpans.length - 1}@@`;
  });

  // URLs are lifted out for the same reason, and for a sharper one: `__` and
  // `*` inside a URL used to be rewritten as emphasis BEFORE linkification saw
  // them, so `https://x.com/a__b__c` yielded href="https://x.com/a" — a
  // different but perfectly valid URL. That href is what `open_external_url`
  // hands to the OS shell, so a link could point somewhere the text did not
  // say. Stashing the destination first makes the emphasis passes blind to it.
  const urls = [];
  const stash = (url) => {
    urls.push(url);
    return `@@U${nonce}${urls.length - 1}@@`;
  };
  out = out
    .replace(
      /(\[[^\]]*\]\()(https?:\/\/[^\s)]+)(\))/g,
      (_match, open, url, close) => open + stash(url) + close
    )
    .replace(
      /(^|[\s(])(https?:\/\/[^\s<)]+)/g,
      (_match, lead, url) => lead + stash(url)
    );

  // Strong runs first and non-greedily, so `**bold *italic* tail**` keeps its
  // inner emphasis instead of failing to match on the nested asterisks. The
  // italic pass then only sees the leftover single delimiters. `(?!\s)` keeps
  // arithmetic like `a * b * c` from turning into emphasis.
  out = out
    .replace(/\*\*\*([\s\S]+?)\*\*\*/g, "<strong><em>$1</em></strong>")
    .replace(/\*\*([\s\S]+?)\*\*/g, "<strong>$1</strong>")
    // `__` needs word boundaries or it eats identifiers: `user__name__id` used
    // to render as `user<strong>name</strong>id`.
    .replace(/(^|[^\w])__([\s\S]+?)__(?!\w)/g, "$1<strong>$2</strong>")
    .replace(/(^|[^*\w])\*(?!\s)([^*\n]+?)\*/g, "$1<em>$2</em>")
    .replace(/~~([\s\S]+?)~~/g, "<s>$1</s>");

  // Only http(s) links are linkified; anything else stays plain text so model
  // output can never produce a `javascript:` or `file:` href.
  const urlPattern = new RegExp(`@@U${nonce}(\\d+)@@`, "g");
  out = out
    .replace(
      new RegExp(`\\[([^\\]]+)\\]\\(@@U${nonce}(\\d+)@@\\)`, "g"),
      (_match, label, index) =>
        `<a href="${urls[Number(index)]}" data-external="true">${label}</a>`
    )
    .replace(urlPattern, (_match, index) => {
      const url = urls[Number(index)];
      return `<a href="${url}" data-external="true">${url}</a>`;
    });

  out = out.replace(
    new RegExp(`@@C${nonce}(\\d+)@@`, "g"),
    (_match, index) => `<code>${codeSpans[Number(index)]}</code>`
  );

  return out;
}


/** Block-level renderer: fences, headings, lists, quotes, rules, tables. */
export function renderMarkdown(source) {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const html = [];

  let index = 0;
  // Every branch below must consume at least one line. This is the guarantee
  // that it does, rather than a promise that it does: an iteration that
  // consumes nothing is an infinite loop, and `renderMarkdown` runs on every
  // streamed token in a frameless always-on-top window. If a future edit ever
  // reintroduces a line that matches no branch, it is rendered as text and the
  // parser moves on.
  let previous = -1;
  while (index < lines.length) {
    if (index === previous) {
      html.push(`<p>${renderInline(lines[index].trim())}</p>`);
      index += 1;
      continue;
    }
    previous = index;

    const line = lines[index];

    // Fenced code - also handles the unterminated fence of a live stream.
    //
    // The opening fence accepts ANY info string, and three OR MORE markers of
    // either kind. It used to demand a bare `[\w+-]*` language and exactly
    // three backticks, which meant "```c#", "``` js", "````", "~~~" and
    // '```js title="a.js"' matched neither this branch nor the paragraph
    // branch below - whose guard excludes every line starting with a fence.
    // `index` then never advanced and the loop spun for ever, freezing a
    // window that has no titlebar and no taskbar entry. A model writing a C#
    // snippet was enough to trigger it, on every streamed token.
    const fence = line.match(/^\s*(`{3,}|~{3,})\s*([^`]*)$/);
    if (fence) {
      // Only the first word of the info string is the language; CommonMark
      // lets the rest be anything and highlighters ignore it.
      const info = (fence[2].trim().split(/\s+/)[0] || "").replace(
        /[^\w+#.-]/g,
        ""
      );
      const language = info ? ` class="language-${escapeHtml(info)}"` : "";
      // A fence closes only on the same marker, at least as long. Otherwise
      // "````" inside a ``` block would end it early.
      const marker = fence[1][0];
      const closer = new RegExp(`^\\s*${marker}{${fence[1].length},}\\s*$`);
      const body = [];
      index += 1;
      while (index < lines.length && !closer.test(lines[index])) {
        body.push(lines[index]);
        index += 1;
      }
      index += 1; // consume the closing fence, if it has arrived
      html.push(
        `<pre><code${language}>${escapeHtml(body.join("\n"))}</code></pre>`
      );
      continue;
    }

    // Blank line.
    if (!line.trim()) {
      index += 1;
      continue;
    }

    // Horizontal rule.
    if (/^\s*([-*_])\s*\1\s*\1[\s\-*_]*$/.test(line)) {
      html.push("<hr />");
      index += 1;
      continue;
    }

    // Heading.
    const heading = line.match(/^\s*(#{1,4})\s+(.*)$/);
    if (heading) {
      const level = heading[1].length;
      html.push(`<h${level}>${renderInline(heading[2].trim())}</h${level}>`);
      index += 1;
      continue;
    }

    // Blockquote.
    if (/^\s*>\s?/.test(line)) {
      const body = [];
      while (index < lines.length && /^\s*>\s?/.test(lines[index])) {
        body.push(lines[index].replace(/^\s*>\s?/, ""));
        index += 1;
      }
      html.push(`<blockquote>${renderMarkdown(body.join("\n"))}</blockquote>`);
      continue;
    }

    // Table: a header row followed by a delimiter row.
    const nextLine = lines[index + 1] || "";
    if (line.includes("|") && /^\s*\|?[\s:-]*-[\s:|-]*\|?\s*$/.test(nextLine)) {
      const cells = (row) =>
        row
          .trim()
          .replace(/^\||\|$/g, "")
          .split("|")
          .map((cell) => cell.trim());

      const head = cells(line);
      index += 2;
      const body = [];
      while (
        index < lines.length &&
        lines[index].includes("|") &&
        lines[index].trim()
      ) {
        body.push(cells(lines[index]));
        index += 1;
      }

      const headHtml = head
        .map((cell) => `<th>${renderInline(cell)}</th>`)
        .join("");
      const bodyHtml = body
        .map(
          (row) =>
            `<tr>${row.map((cell) => `<td>${renderInline(cell)}</td>`).join("")}</tr>`
        )
        .join("");

      html.push(
        `<table><thead><tr>${headHtml}</tr></thead><tbody>${bodyHtml}</tbody></table>`
      );
      continue;
    }

    // Lists. Indentation-aware: an item owns every following line indented
    // past its marker, so nested lists, multi-paragraph items and fenced code
    // inside an item all survive by recursing through this same parser.
    const marker = line.match(/^(\s*)([-*+]|\d+[.)])\s+/);
    if (marker) {
      const baseIndent = marker[1].length;
      const ordered = /\d/.test(marker[2]);
      const items = [];

      while (index < lines.length) {
        const item = lines[index].match(/^(\s*)([-*+]|\d+[.)])\s+(.*)$/);
        // A marker at a different indent belongs to an enclosing or nested
        // list; a different kind starts a separate list.
        if (!item || item[1].length !== baseIndent) break;
        if (/\d/.test(item[2]) !== ordered) break;

        const head = item[3];
        const rest = [];
        index += 1;

        while (index < lines.length) {
          const next = lines[index];
          if (!next.trim()) {
            // A blank line only stays inside the item when indented content
            // follows it; otherwise the list has ended.
            const after = lines[index + 1] || "";
            const afterIndent = after.match(/^(\s*)/)[1].length;
            if (!after.trim() || afterIndent <= baseIndent) break;
            rest.push("");
            index += 1;
            continue;
          }
          if (next.match(/^(\s*)/)[1].length <= baseIndent) break;
          rest.push(next);
          index += 1;
        }

        // Dedent continuation lines by their own common indent so nested
        // fences keep their original relative shape.
        const indents = rest
          .filter((l) => l.trim())
          .map((l) => l.match(/^(\s*)/)[1].length);
        const strip = indents.length ? Math.min(...indents) : 0;
        items.push([head, ...rest.map((l) => l.slice(strip))]);
      }

      const tag = ordered ? "ol" : "ul";
      const itemsHtml = items
        .map((buffer) => {
          // A one-line item stays inline so plain lists are not padded with
          // paragraph margins; anything richer goes back through the block
          // parser, with its leading paragraph unwrapped.
          if (buffer.length === 1) return `<li>${renderInline(buffer[0])}</li>`;
          const body = renderMarkdown(buffer.join("\n")).replace(
            /^<p>([\s\S]*?)<\/p>/,
            "$1"
          );
          return `<li>${body}</li>`;
        })
        .join("");
      html.push(`<${tag}>${itemsHtml}</${tag}>`);
      continue;
    }

    // Paragraph - greedily absorb the following plain lines.
    const paragraph = [];
    while (
      index < lines.length &&
      lines[index].trim() &&
      !/^\s*(#{1,4}\s|>|`{3,}|~{3,}|[-*+]\s|\d+[.)]\s)/.test(lines[index])
    ) {
      paragraph.push(lines[index].trim());
      index += 1;
    }
    html.push(`<p>${renderInline(paragraph.join(" "))}</p>`);
  }

  return html.join("");
}
