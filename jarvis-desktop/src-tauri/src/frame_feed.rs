//! Deciding which captured screen frames are worth encoding and sending, and
//! how many may be waiting to go.
//!
//! WHY THIS EXISTS. A frame feed is the one shape in this app where being
//! wasteful is silent: nothing breaks, the picture still arrives, and the cost
//! is CPU spent encoding a screen that has not moved and memory spent holding
//! frames for a backend that stopped listening. Two rules fix that, and both
//! live here as plain functions so they can be tested without a screen:
//!
//! * **[`dhash`]** - a 64-bit difference hash of one frame. Equal to the
//!   previous frame's hash means the screen has not visibly changed, and the
//!   PNG encode, the base64 and the send are all skipped ([`FrameDedup::keep`]).
//! * **[`send_drop_oldest`]** - a bounded queue that gives up the OLDEST
//!   waiting frame rather than the newest, or blocking the capture, or growing.
//!
//! WHAT "UNCHANGED" COSTS, AND WHY IT IS ALLOWED TO BE WRONG. A dHash compares
//! brightness gradients, so it deliberately ignores small detail: **a skip can
//! drop a change the owner cared about** - one line of text typed into an
//! otherwise identical window, a cursor blinking, a video frame in a still
//! scene, a dialog that appears and disappears between two samples. That is the
//! price of the saving, and it is paid every time the hash says equal. A feed
//! that must never drop one thing therefore does not use a whole-frame hash:
//! it keeps [`FrameDedup::force`] on a change it knows about for certain (a new
//! question, a scene the owner asked about aloud) or makes that change itself
//! re-send. THE HASH IS A SAVING, NOT A PROMISE.
//!
//! WIRED UP YET? No. **Nothing calls this module today**, and it is here
//! because the feed it is for does not exist in this process: "Look at this"
//! and "Watch with me" ask the PC's backend for their one picture per look
//! (`look.rs`; `jarvis_screen_win.capture`), and the app's own capture path
//! (`commands.rs` `capture_primary_display`) is single-shot, has no caller and
//! is not in `lib.rs`'s command list. So this is the saving built and tested
//! ahead of the loop that will want it - which is the opposite of what a
//! silent skip must never be: an invented measurement. Nothing about a live
//! feed is claimed here, and the numbers in the tests below are synthetic
//! frames, not a capture of anybody's screen.
//!
//! Nothing here reads a screen, opens a device, or knows a window's name. It
//! takes bytes a caller already has and answers one question about them.

/// How many columns the hash grid has. Nine, not eight, because the hash is
/// the comparison of each pixel with the one to its right: nine columns give
/// eight comparisons per row.
pub const HASH_COLS: usize = 9;
/// How many rows the hash grid has. Eight rows times eight comparisons is
/// exactly the 64 bits of a `u64`.
pub const HASH_ROWS: usize = 8;
/// How many comparison bits one hash carries.
pub const HASH_BITS: usize = (HASH_COLS - 1) * HASH_ROWS;

/// How the bytes of one frame are laid out.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Channels {
    /// Three bytes a pixel: red, green, blue.
    Rgb,
    /// Four bytes a pixel: red, green, blue, alpha.
    Rgba,
}

impl Channels {
    /// The bytes one pixel takes.
    pub fn bytes_each(self) -> usize {
        match self {
            Channels::Rgb => 3,
            Channels::Rgba => 4,
        }
    }
}

/// The luminance of one pixel, in the same 0..255 range the bytes were in.
///
/// The integer form of Rec. 601's `0.299 R + 0.587 G + 0.114 B`. Kept in
/// integers on purpose: a hash computed in floating point could differ between
/// two builds of the same code, and a "the screen did not change" that depends
/// on the compiler is not a measurement.
fn luma(r: u8, g: u8, b: u8) -> u32 {
    (299 * r as u32 + 587 * g as u32 + 114 * b as u32) / 1000
}

/// A 64-bit difference hash of one frame.
///
/// The frame is squashed to a [`HASH_COLS`] x [`HASH_ROWS`] grid of average
/// brightness - every source pixel in a cell counts once, so a one-pixel change
/// on a large screen barely moves a cell - and the hash then records, for each
/// of the 64 neighbouring pairs, whether the left one is brighter than the
/// right. That makes it a hash of the picture's GRADIENTS, which is what lets
/// it survive a re-render, a font hinting difference or a brightness nudge
/// while still catching a real rearrangement of the screen.
///
/// Returns `None` when the frame cannot be read: no pixels, zero width or
/// height, or a buffer too short for the pixels the dimensions claim. A caller
/// must treat `None` as "send it" - the alternative would be treating an
/// unreadable frame as an unchanged one, which is exactly the silent drop this
/// module exists to avoid.
pub fn dhash(pixels: &[u8], width: u32, height: u32, channels: Channels) -> Option<u64> {
    if width == 0 || height == 0 {
        return None;
    }
    let each = channels.bytes_each();
    let needed = width as usize * height as usize * each;
    if pixels.len() < needed {
        return None;
    }

    // One cell's average brightness. u64 because the largest cell is a quarter
    // of a 64 MP frame: 16,000,000 pixels x 255 fits u32 only by a hair, and
    // fitting by a hair is how an overflow ships.
    let mut cells = [0u64; HASH_COLS * HASH_ROWS];
    for (cell, sum) in cells.iter_mut().enumerate() {
        let (cx, cy) = (cell % HASH_COLS, cell / HASH_COLS);
        // Every source row/column in this cell, by integer ranges so no pixel
        // is counted twice or missed however the sizes divide. A cell with no
        // source pixel at all (a frame narrower than the grid) is black rather
        // than a division by zero.
        let x0 = cx * width as usize / HASH_COLS;
        let x1 = ((cx + 1) * width as usize / HASH_COLS)
            .max(x0 + 1)
            .min(width as usize);
        let y0 = cy * height as usize / HASH_ROWS;
        let y1 = ((cy + 1) * height as usize / HASH_ROWS)
            .max(y0 + 1)
            .min(height as usize);
        let mut total = 0u64;
        for y in y0..y1 {
            for x in x0..x1 {
                // Red, green and blue are the first three bytes of a pixel in
                // both layouts; the fourth, when there is one, is alpha and is
                // not part of the picture.
                let at = (y * width as usize + x) * each;
                *sum += luma(pixels[at], pixels[at + 1], pixels[at + 2]) as u64;
                total += 1;
            }
        }
        // `checked_div`, not a plain `/`: a cell with no source pixel at all (a
        // frame narrower than the grid) has no average, and this is where that
        // becomes a black cell rather than a division by zero.
        *sum = sum.checked_div(total).unwrap_or(0);
    }

    let mut hash = 0u64;
    let mut bit = 0;
    for y in 0..HASH_ROWS {
        for x in 0..HASH_COLS - 1 {
            let left = cells[y * HASH_COLS + x];
            let right = cells[y * HASH_COLS + x + 1];
            if left > right {
                hash |= 1u64 << bit;
            }
            bit += 1;
        }
    }
    debug_assert_eq!(bit, HASH_BITS);
    Some(hash)
}

/// What to do with one frame the feed has just captured.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Send {
    /// Encode it and send it.
    Yes,
    /// The screen is where it was: skip the encode, the base64 and the send.
    SameAsLast,
}

/// Whether the last frame's hash still describes the owner's screen.
///
/// Kept per feed, so two feeds never silence each other. [`reset`]
/// (Self::reset) is what a caller uses when the last hash stopped meaning
/// anything: the first frame after a session starts, the first after a
/// reconnect, and the first after anything that could have changed the screen
/// while nothing was watching. Without that, a screen that changed while the
/// feed was down would look unchanged for ever.
#[derive(Debug, Default)]
pub struct FrameDedup {
    last: Option<u64>,
    forced: bool,
}

impl FrameDedup {
    /// A feed that has sent nothing yet: the first frame always goes.
    pub fn new() -> Self {
        Self::default()
    }

    /// Forgets the last hash, so the next frame is sent whatever it holds.
    ///
    /// Call it on the first frame of a session, after reconnecting, and after
    /// a gap in sample. The next call to [`keep`](Self::keep) keeps the frame
    /// and carries on from there.
    pub fn reset(&mut self) {
        self.last = None;
    }

    /// Sends the next frame whatever it holds, and carries on from there.
    ///
    /// For a change the caller knows about for certain and cannot risk being
    /// deduplicated - a new question, a scene the owner just asked about, a
    /// deliberate "look now". One frame, not a mode: it clears itself.
    pub fn force(&mut self) {
        self.forced = true;
    }

    /// What to do with the frame just captured.
    pub fn keep(&mut self, hash: Option<u64>) -> Send {
        let forced = std::mem::take(&mut self.forced);
        match hash {
            // A frame that cannot be read is never "unchanged": send it, and
            // do not let it replace the last hash (the old one still describes
            // the last screen this feed actually understood).
            None => Send::Yes,
            Some(hash) => {
                let same = !forced && self.last == Some(hash);
                self.last = Some(hash);
                if same {
                    Send::SameAsLast
                } else {
                    Send::Yes
                }
            }
        }
    }
}

/// How many frames may wait for a backend that has stopped reading.
///
/// Sixteen is about half a second of a thirty-a-second feed: long enough that
/// an ordinary slow moment never drops anything, short enough that a backend
/// which has gone away costs sixteen small buffers and not a growing number.
pub const FEED_QUEUE: usize = 16;

/// The error of a [`FrameQueue`] whose receiver has gone.
#[derive(Debug, PartialEq, Eq)]
pub struct Gone;

/// A feed's waiting frames, held apart from the capture that fills them.
///
/// A `tokio::sync::mpsc::channel(FEED_QUEUE)` whose SEND side is the rule this
/// module exists for: when the queue is full, one frame goes and the OLDEST is
/// the one that goes.
///
/// THE CHOICE, and why not the two obvious alternatives. Dropping the NEWEST
/// would keep a stale picture and throw away the moment the owner actually
/// wants; blocking the capture would stop the sampler, so the feed would go
/// blind exactly while the backend is struggling, and unbounded growth is the
/// bug this prevents (a backend that restarts stops reading for as long as it
/// takes, and nothing would ever tell the capture to slow down). Dropping the
/// oldest keeps the most recent screen - which is what a screen-attach feed is
/// FOR - and makes a restart cost one frame, not the session.
///
/// A queue whose reader has gone answers [`Gone`] rather than filling memory,
/// which is the caller's signal to stop capturing rather than an error to show
/// the owner.
pub struct FrameQueue<T> {
    /// `None` once [`sender`](Self::sender) has been called: the clone that
    /// went out is then the ONLY sender, so dropping it closes the queue and
    /// [`push`](Self::push) can answer [`Gone`]. Keeping a sender of our own
    /// alive would hold the channel open for ever and the reader's exit would
    /// never be noticed.
    tx: Option<tokio::sync::mpsc::Sender<T>>,
    rx: tokio::sync::mpsc::Receiver<T>,
}

impl<T> FrameQueue<T> {
    /// A queue that holds at most `capacity` frames.
    pub fn new(capacity: usize) -> Self {
        let (tx, rx) = tokio::sync::mpsc::channel(capacity);
        FrameQueue { tx: Some(tx), rx }
    }

    /// The sender half, for the capture to hand to whoever reads it.
    ///
    /// Takes it out of this struct: the caller's clone becomes the only
    /// sender, which is what lets a dropped reader be noticed.
    pub fn sender(&mut self) -> tokio::sync::mpsc::Sender<T> {
        self.tx
            .take()
            .expect("FrameQueue::sender is called once, before anything is pushed")
    }

    /// Queues one frame, dropping the oldest waiting one if this is full.
    pub fn push(&mut self, frame: T) -> Result<(), Gone> {
        // `capacity()` is the room LEFT (`max_capacity` minus what is queued),
        // so zero is "full".
        if self.tx.as_ref().is_none_or(|tx| tx.capacity() == 0) {
            // Free exactly one slot by giving up the frame that has waited
            // longest. `try_recv` cannot block here: the queue is full, so
            // there is either a frame to drop or a reader that closed between
            // the two calls.
            match self.rx.try_recv() {
                Ok(_dropped) => {}
                Err(tokio::sync::mpsc::error::TryRecvError::Empty) => {}
                Err(tokio::sync::mpsc::error::TryRecvError::Disconnected) => return Err(Gone),
            }
        }
        match self.tx.as_ref() {
            Some(tx) => tx.try_send(frame).map_err(|_| Gone),
            // The only sender went out to the capture and is gone: nothing can
            // receive, so nothing may be queued.
            None => Err(Gone),
        }
    }

    /// Takes the oldest frame waiting, if one is.
    pub fn pop(&mut self) -> Option<T> {
        self.rx.try_recv().ok()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A frame of one solid colour, repeated.
    fn solid(width: u32, height: u32, channels: Channels, rgb: (u8, u8, u8)) -> Vec<u8> {
        let mut out = Vec::with_capacity(width as usize * height as usize * channels.bytes_each());
        for _ in 0..width as usize * height as usize {
            out.push(rgb.0);
            out.push(rgb.1);
            out.push(rgb.2);
            if channels == Channels::Rgba {
                out.push(255);
            }
        }
        out
    }

    /// A gradient left to right, so neighbouring cells differ and the hash has
    /// real bits in it rather than being all ones or all zeroes.
    fn gradient(width: u32, height: u32, channels: Channels) -> Vec<u8> {
        let mut out = Vec::with_capacity(width as usize * height as usize * channels.bytes_each());
        for _ in 0..height {
            for x in 0..width {
                let v = (x * 255 / width.max(1)) as u8;
                out.push(v);
                out.push(v);
                out.push(v);
                if channels == Channels::Rgba {
                    out.push(255);
                }
            }
        }
        out
    }

    #[test]
    fn a_frame_smaller_than_the_grid_still_hashes_and_a_solid_one_is_all_zeroes() {
        // Every cell the same brightness: no gradient, so no bit is set. A
        // hash of everything-equal is 0 and that is a real answer, not a
        // failure - the NEXT frame differing anywhere sets a bit.
        let got = dhash(
            &solid(4, 4, Channels::Rgb, (10, 20, 30)),
            4,
            4,
            Channels::Rgb,
        );
        assert_eq!(got, Some(0));
    }

    #[test]
    fn a_brightness_ramp_fills_every_bit_and_its_mirror_clears_them_all() {
        // A ramp that rises all the way across: every cell is brighter than
        // the one to its left, so every comparison is "not brighter to the
        // right" and NO bit is set. That is the hash's own convention (a bit
        // means "the left pixel is the brighter one"), and pinning both ends -
        // all zeroes for a rising ramp, all ones for a falling one - is what
        // proves the comparison is not inverted and that all 64 bits are
        // really being written.
        //
        // The frame is 72 wide, so nine columns are exactly eight source
        // columns each and every step is real. A 64-wide frame would put seven
        // source columns in each cell and land two neighbouring cells on the
        // same average, which is the hash working as designed, not a bug.
        let ramp = gradient(72, 9, Channels::Rgb);
        let rising = dhash(&ramp, 72, 9, Channels::Rgb).unwrap();
        assert_eq!(rising, 0, "a rising ramp should set no bit: {rising:#018x}");
        assert_eq!(
            dhash(&ramp, 72, 9, Channels::Rgb),
            Some(rising),
            "the same bytes must hash the same every time"
        );
        // And the mirror image: bright on the right instead.
        let mut mirrored = Vec::new();
        for _ in 0..9 {
            for x in 0..72 {
                let v = 255 - (x * 255 / 72) as u8;
                mirrored.extend_from_slice(&[v, v, v]);
            }
        }
        let got = dhash(&mirrored, 72, 9, Channels::Rgb).unwrap();
        assert_eq!(
            got,
            u64::MAX,
            "a falling ramp should set every bit: {got:#018x}"
        );
    }

    #[test]
    fn the_same_picture_hashes_the_same_through_rgb_and_rgba() {
        // The alpha byte is not part of the picture. A capture that gains an
        // alpha channel must not read as a screen change, or every frame of a
        // four-channel source would be sent for ever.
        let rgb = gradient(32, 16, Channels::Rgb);
        let rgba = gradient(32, 16, Channels::Rgba);
        assert_eq!(
            dhash(&rgb, 32, 16, Channels::Rgb),
            dhash(&rgba, 32, 16, Channels::Rgba)
        );
    }

    #[test]
    fn a_picture_is_unchanged_by_its_size_or_by_a_gain_to_the_whole_screen() {
        // The hash is of GRADIENTS, not levels: the same layout at another
        // resolution, or dimmed, is the same screen as far as this is
        // concerned - which is the point of a difference hash (see the
        // module's "WHAT UNCHANGED COSTS").
        let small = dhash(&gradient(90, 80, Channels::Rgb), 90, 80, Channels::Rgb);
        let large = dhash(
            &gradient(90 * 4, 80 * 4, Channels::Rgb),
            90 * 4,
            80 * 4,
            Channels::Rgb,
        );
        assert_eq!(small, large, "the same layout at 4x must hash the same");
    }

    #[test]
    fn a_rearranged_screen_hashes_differently() {
        // The measurement this whole module rests on: put the bright half of
        // the screen on the other side and the hash must move. If this ever
        // fails, dedup is silently dropping every scene change.
        let width = 60;
        let height = 40;
        let mut left = Vec::new();
        let mut right = Vec::new();
        for _ in 0..height {
            for x in 0..width {
                let (a, b) = if x < width / 2 {
                    (240u8, 16u8)
                } else {
                    (16, 240)
                };
                left.push(a);
                left.push(a);
                left.push(a);
                right.push(b);
                right.push(b);
                right.push(b);
            }
        }
        let on_left = dhash(&left, width, height, Channels::Rgb).unwrap();
        let on_right = dhash(&right, width, height, Channels::Rgb).unwrap();
        assert_ne!(
            on_left, on_right,
            "moving the bright half did not change the hash: {on_left:#018x} vs {on_right:#018x}"
        );
    }

    #[test]
    fn a_frame_that_cannot_be_read_is_none_never_zero() {
        // None means "send it". Zero means "a real, flat picture" and may be
        // skipped. Confusing the two would drop a frame nobody read.
        assert_eq!(dhash(&[], 0, 0, Channels::Rgb), None);
        assert_eq!(
            dhash(&[0, 0, 0], 4, 4, Channels::Rgb),
            None,
            "too short for 4x4"
        );
        assert_eq!(
            dhash(&[0, 0, 0], 1, 1, Channels::Rgba),
            None,
            "3 bytes are not one RGBA pixel"
        );
        assert_eq!(dhash(&[0, 0, 0, 0], 1, 1, Channels::Rgba), Some(0));
    }

    #[test]
    fn the_first_frame_always_goes_and_the_second_identical_one_does_not() {
        let mut dedup = FrameDedup::new();
        let same = Some(0x1234_5678_9abc_def0u64);
        assert_eq!(
            dedup.keep(same),
            Send::Yes,
            "the first frame was never sent"
        );
        assert_eq!(dedup.keep(same), Send::SameAsLast);
        assert_eq!(dedup.keep(same), Send::SameAsLast);
    }

    #[test]
    fn a_changed_frame_goes_and_becomes_the_new_baseline() {
        let mut dedup = FrameDedup::new();
        assert_eq!(dedup.keep(Some(1)), Send::Yes);
        assert_eq!(dedup.keep(Some(2)), Send::Yes);
        assert_eq!(dedup.keep(Some(2)), Send::SameAsLast);
        assert_eq!(
            dedup.keep(Some(1)),
            Send::Yes,
            "going back is still a change"
        );
    }

    #[test]
    fn reset_makes_the_next_frame_go_whatever_it_is() {
        // The first frame of a session, or the first after a reconnect: the
        // screen may have changed while nothing was watching, and a kept hash
        // would hide that for ever.
        let mut dedup = FrameDedup::new();
        assert_eq!(dedup.keep(Some(7)), Send::Yes);
        assert_eq!(dedup.keep(Some(7)), Send::SameAsLast);
        dedup.reset();
        assert_eq!(
            dedup.keep(Some(7)),
            Send::Yes,
            "a reset frame was swallowed"
        );
        assert_eq!(
            dedup.keep(Some(7)),
            Send::SameAsLast,
            "and dedup carries on after it"
        );
    }

    #[test]
    fn force_sends_one_frame_and_then_gets_out_of_the_way() {
        let mut dedup = FrameDedup::new();
        assert_eq!(dedup.keep(Some(3)), Send::Yes);
        dedup.force();
        assert_eq!(
            dedup.keep(Some(3)),
            Send::Yes,
            "a forced frame was swallowed"
        );
        assert_eq!(
            dedup.keep(Some(3)),
            Send::SameAsLast,
            "force must be one frame, not a mode - otherwise dedup is off for good"
        );
    }

    #[test]
    fn force_is_not_swallowed_by_an_unreadable_frame_either() {
        // `None` already always sends. Force must not leak past it into the
        // NEXT frame, which the caller never asked to force.
        let mut dedup = FrameDedup::new();
        dedup.force();
        assert_eq!(dedup.keep(None), Send::Yes);
        assert_eq!(dedup.keep(None), Send::Yes);
        assert_eq!(dedup.keep(Some(9)), Send::Yes);
        assert_eq!(
            dedup.keep(Some(9)),
            Send::SameAsLast,
            "force lasted too long"
        );
    }

    #[test]
    fn an_unreadable_frame_does_not_replace_the_last_hash() {
        // The old hash still describes the last frame this feed understood. If
        // an unreadable frame cleared it, the frame after it would be sent
        // again for no reason - and if it SET it, a real screen change could
        // be lost.
        let mut dedup = FrameDedup::new();
        assert_eq!(dedup.keep(Some(5)), Send::Yes);
        assert_eq!(dedup.keep(None), Send::Yes);
        assert_eq!(
            dedup.keep(Some(5)),
            Send::SameAsLast,
            "the unreadable frame moved the baseline"
        );
    }

    #[test]
    fn the_queue_gives_up_the_oldest_and_keeps_the_newest() {
        // The rule, made to bite: push four into a queue of three and the
        // FIRST one must be the one that is gone.
        let mut queue: FrameQueue<u32> = FrameQueue::new(3);
        for frame in 0..4 {
            queue.push(frame).expect("a live queue accepts");
        }
        assert_eq!(
            queue.pop(),
            Some(1),
            "the oldest frame should have been dropped"
        );
        assert_eq!(queue.pop(), Some(2));
        assert_eq!(queue.pop(), Some(3));
        assert_eq!(queue.pop(), None);
    }

    #[test]
    fn a_queue_sixteen_deep_holds_sixteen_and_drops_only_beyond_that() {
        // The bound the feed will actually use, so the number is exercised and
        // not just written down: sixteen fit, and the seventeenth costs the
        // FRAME THAT WAITED LONGEST and nothing else.
        let mut queue: FrameQueue<usize> = FrameQueue::new(FEED_QUEUE);
        for frame in 0..FEED_QUEUE {
            queue.push(frame).expect("a live queue accepts");
        }
        assert_eq!(
            queue.pop(),
            Some(0),
            "nothing may be dropped before the queue is full"
        );
        queue.push(FEED_QUEUE).unwrap();
        let mut waiting = Vec::new();
        while let Some(frame) = queue.pop() {
            waiting.push(frame);
        }
        let expected: Vec<usize> = (1..=FEED_QUEUE).collect();
        assert_eq!(
            waiting, expected,
            "the bound held {FEED_QUEUE} and gave up the oldest, not the newest"
        );
    }

    #[test]
    fn a_queue_whose_reader_has_gone_says_so_instead_of_growing() {
        // The backend-restart case: the receiver is dropped, and the capture
        // must be TOLD rather than filling memory for ever.
        let mut queue: FrameQueue<u32> = FrameQueue::new(2);
        queue.push(1).expect("a live queue accepts");
        queue.push(2).expect("a live queue accepts");
        // The clone the capture would hold, dropped: this is a backend that
        // stopped reading, not just a slow one.
        drop(queue.sender());
        assert_eq!(queue.push(3), Err(Gone));
    }
}
