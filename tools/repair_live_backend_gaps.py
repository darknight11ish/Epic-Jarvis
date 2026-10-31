"""repair_live_backend_gaps.py - put back the base-file pieces this PC's
install never received, without touching anything else.

WHY THIS EXISTS (measured 2026-10-30 on the owner's PC)

`main` is green and the deploy through `tools/reconcile_live_backend.py` moved
the live backend onto today's SHIPPED modules and HUD deltas with 0 refusals.
Four pieces still could not arrive, because they are **base-file or
patch-carried** content that only `scripts/apply-patches.ps1` would carry - and
that patcher refuses 37 patches on this drifted install:

1. **jarvis_gate.py** - the two `_RISK` rows for the Android app builder
   (`app_build_android`, `app_install_android`). `jarvis-backend/jarvis_gate.py`
   (the published base) has them; the live file predates them. Without them
   `jarvis_gate.risk_for()` classifies the action as unknown, and a card for an
   unknown action is raised `approve_ok: false` - the owner cannot approve an
   app build at all (found in the field test: the card appeared but only Deny
   worked).
2. **jarvis_hud.py** - the `POST /api/history/pin` and
   `POST /api/history/archive` routes (added by later revisions of
   `chat-history.patch`). The live HUD's history route tuple ends at
   `/api/history/mark`, so both answer 404; the module `jarvis_chat_log.py`
   already has the handlers (it was synced by the deploy).
3. **jarvis_gate.py** - the card timer added by `show-card-timer.patch` (the
   owner's ruling of 2026-10-30: "if there is a card with a limited time of
   any kind, be sure to put the timer on it"). `pending()` never sends
   `expires_in` on this install, so no screen can draw a countdown and a
   routine card can still run out silently - the field test hit exactly that.
4. **jarvis_gate.py** - #1008's unclassified-action rule (Gemini's Q2 ruling
   of 2026-10-30, `unknown-risk-approvable.patch`): an action with no `_RISK`
   row is given the worst case, shown with one plain warning line, approved
   only through the human check, and forced to tier "ask"; the eight reads
   that ran unattended get their own rows, so the rule changes nothing the
   owner uses today. SIX disjoint hunks (the fifth and sixth are DEF-021's
   file-wins tier fix and its revised forced-ask block, 2026-10-31). The
   first one CANNOT be replayed on this PC by
   `tools/reconcile_live_backend.py`: the `gate` repair above put the
   app-builder rows immediately after the table's opening brace, so that
   hunk's two-line pre-image no longer exists here. The change is therefore
   carried as six exact pieces, applied as ONE write (one backup, one
   compile), so it cannot land half done.

All four repairs are exact, anchored, idempotent edits. Nothing is guessed: if
an anchor is missing or appears more than once the tool refuses; if a repair is
already present it says so and writes nothing; every write is backed up first
and the result must compile or it is rolled back.

THE CARD TIMER IS TWO HUNKS, NOT ONE (measured 2026-10-30). The patch it copies
both inserts the `expires_in` block AND changes `pending()`'s SELECT line so the
row it reads has a `waited_until` column. A repair that inserts only the block
can never run - the column is not in the dict, `d.pop("waited_until", ...)` is
always None - and its own probes would still call it applied. So a `Repair` may
carry `extra_edits`: further exact old/new pairs applied in the SAME write,
with the same one backup and one compile. A file with only one of the hunks is
REFUSED rather than re-applied, so this tool can never duplicate the block.

THE UNCLASSIFIED-ACTION RULE IS SIX PIECES, AND ITS FIRST ONE IS LIVE-SHAPED
(measured 2026-10-30, read-only dry run; extended 2026-10-31 for DEF-021).
`unknown-risk-approvable.patch` adds the eight rows at the TOP of `_RISK`,
changes the `_UNKNOWN_RISK` fallback, adds to `risk_for`'s docstring and
`notice_for`'s body, makes `_tiers()` let the owner's explicit
`[autonomy.tiers]` line win over `_SYNTH_TIERS` (with `_file_tier_names()`
for check()'s exemption), and forces an unclassified action to "ask" in
`check()`. Every hunk pre-image except the first appears exactly once in the
published gate; on the file measured 2026-10-30 (when the patch still had five
hunks) the first did not, because the `gate` repair above inserted the
app-builder rows immediately after that opening brace. So a `Repair` may also
carry ordered `pieces` - several exact old/new pairs, still one write, one
backup, one compile - and this repair's first piece is anchored on the brace
alone so it applies to the live shape AND to a fresh install. The sixth piece
is DEF-021's `_tiers()` / `_file_tier_names()` hunk; its pre-image is the
owner's own `_tiers()` code, which no patch writes, and the `check()` piece's
post-image is DEF-021's revised forced-ask block.

THE LIVE LINEAGE IS HASH-ADDRESSED (Gemini ruling (a), 2026-10-31). The
published-base pre-image the six pieces serve and the owner's LIVE gate are
DIFFERENT lineages: a live gate that already carries the five #1008 pieces and
not DEF-021 was the half state this tool used to have to refuse on the owner's
PC. `UNKNOWN_RISK` now also carries `lineages`, a BOUNDED, hash-keyed table
(`LIVE_LEGACY_GATES`) of the real live gates this tool has proved: the 5-hunk
#1008 gate (`3e9b8068…`), the pre-#1008 gate (`059e1c7c…`, the five #1008
pieces reversed out of the #1023 post-image), the two 2026-10-30 live backups
(`7dff103a…`, `7b14b682…`) and the 2026-10-19 install record (`fba83b80…`).
Each row carries the stored exact patch to the #1023 post-image
(`39a0c407…`); a listed gate is brought to that post-image and the result is
hash-verified BEFORE the one write, a gate already at `39a0c407…` is the
idempotent no-op, and an unrecognised live-sized gate is REFUSED with its hash
printed - never guessed. This is NOT a general in-place patch-stack rewriter:
the table is bounded, and adding a lineage means adding its verified bytes and
its patch. New features continue to arrive as drop-in `install()` plugins, so
these base files rarely need a new patch at all.

This is a REPAIR for drifted installs, not a new mechanism to prefer: once the
patch stack can be applied again (`apply-patches.ps1` succeeds), the base files
carry every piece and this tool reports "already" and does nothing.

USAGE

    python -B tools/repair_live_backend_gaps.py --backend-path "<live>"           # check only
    python -B tools/repair_live_backend_gaps.py --backend-path "<live>" --apply   # write (after a clean check)
    ... --only gate           # one repair
    ... --only history
    ... --only timer
    ... --only unknown-risk

Exit codes: 0 = every requested repair is present (or was applied);
1 = something is missing in check mode; 2 = refused (anchor missing/ambiguous,
or the rewritten file did not compile).
"""
from __future__ import annotations

import argparse
import py_compile
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import base64
import hashlib
import re
import zlib


#: The #1023 post-image every accepted live lineage is brought to (sha256).
LIVE_GATE_TARGET_SHA256 = (
    "39a0c407049e935557fad3b6d3db4ab81ba3d230a2dfc2b0384f239b818b410a"
)

#: Live-lineage gates this repair accepts, by sha256, each with the exact
#: stored live->#1023 patch (zlib+base85, decoded in `_legacy_patch`). The
#: table is bounded on purpose (Gemini ruling (a), 2026-10-31): it accepts the
#: two gates the ruling names and the three real backups of that lineage; it
#: is not a general in-place patch-stack rewriter, and an unrecognised
#: live-lineage hash is refused.
LIVE_LEGACY_GATES = {
    # 5-hunk #1008 live gate (3e9b8068…)
    "3e9b80689239f5f06f8c85d4fd5caea40912b37c60c6083519f3a1b91cc33041": (
        "c-pO4ZFAek5&q6!u|+y#AS6&pZsG|uZcWGZm@^8QvDi4Ntf5Z8fxHmB!{830*-ZX>ckcl5K)qN_OMMUt9v<w=v(N4_6L}7Cy"
        "c7o5-+p7&t<Z}lGdwAGaC3B_7sv6PQ@wt_fA{38R}i26{l$yH*%|chn{Q6w)vF%Rs|rR%p|-$3@w7HVNl-Z$r3!c!UXJ2_v-"
        "m$J@pp@l@yFz<A3cMuFe_lyQbU-09ew=gNB#9*g8@`Lxrll|e;LnVVFa&qm{)AWx2jqXVOA12D=ssUnk#q-Qzdx>@jrkr40|"
        "yd69mD0#er@H!)^*bfLm6G3?0c57)hvQ#Z$GELi5ZW)20$~2{8mye#@(%G0@?qtQ3Y70|?k!qm@kV%!-anWk5(+{5(3Jyjjd"
        "A<M$T`AvBnZ)5Cyi2&4rZIH((*vRZRsV0NXVn;B>fStZO4N>zw-2YRLIB7;Ju>w$elE$MxNZuR<~^KalRH~78UN?twFn3EE5"
        "kqw2A9KV(lZBKfA2lgf5cr+3Y?y2E;G!hQ#GvR0*n7<pt+sXMDK1`+;F#CD@-d>u|X6G;;y~Z!XH{-YQ$=T@u&Q8w0jZaVF="
        "ciEu*Ncl^r}KBt&}#>_Qbne1^oaHtJPaa~yoxQCk&~=0jD}oQAd!@Glwp}w+*-y`Vkh2|JG4ty8zt3dmslcSK^Ua0Nb7<bg+"
        "WEu(gBR-hHq50TWGw@?R7*G`3{Yopud<Fhi4Rq4Oof!#AuG*&e2!0H5bGItuP-h>#$uZ*jCC=d~MpvVl0)tX=bG`_|AtF%K+"
        ")25k;C}2MRN^#XJ};F@H>EaGkDrx(=i3XV&+WXED=jhlC}+u~kW?NYHChmS`RSgwa4S??DO7JzA2{mK-bY=X;2z=mVdf^?0m"
        "cBD0oRkM&OCKkXRnN&wy8QZn{<AMg{IspDK!+Ca&c7>)wDm|0eB@m>UOZ?YN3z;7W_Wb4QpZJF=zq;fV}i?k6%fsbBe{K(*r"
        "K~zGuOjk@UQE{kltw@?`H+1jlm7{v?l?_Dhf6$grq;0?p3}3!Y3dOR;{zw=dfGV~nsAS1a7_^MT3j6(!$X&DKa~A+<@cSR`U"
        "j8ZNrGc^ihxzkttGKBvNhhspsoLNZ@KgWriS#z~E2y!Eh=zrFOBIclCBpEH4kHiz7Vk!Z32&o>bfyd=bZ*Nl-zR*=<(l;UmL"
        "hX|M^<c98ZFt|nA9b4=02+$hwu=|Mz3$X3uV)`n1!Y1)B23&*k*hgZj0VYq=fM=Kb=p0n9LjI%6)|*=Z^(pFJk{9-rVdSC^V"
        ">Q<XtOc(a=JYBE^>bhZ1yPP9RW*B-Y=SigMo$u+}w9XLD%l+mi<?WfX~)`>j$q^Bb{n6}zuu(nl8oD-^CE?13s1l2tovJ5^_"
        "68?~FXU|NfuL`=ErcID(eCYcM+>)?B|&eq`G1ggwKud&~)IWIekeXQ0A*dB&t#NyQ7I}1nzZ0HEKwM-)kHGNOf+)<{no32E<"
        "YMmy!rUtPxfgRI2O@SkLR82flS#KR)NOw4-L#HOK;6;vn%u&`g(PN+T=+NP<QuO~{O3^<mYji9O@6`(@4-d&k)C&HwZrt|(Z"
        ";W&NSYW6YWu-78q5C(afDR5t-+eu)8ckgm{E}ec26KKjv}5Yo$%}6WXWv5q?DXXM;Q5RFm`bm&um*~JXm#Hb<4%{>Y^Q0qX^"
        "BmVtOS;!OCgcahoc0nsc#5<%;2QeD97=JJy>Xnjd)Zs)Y^D%e89GKGHNY&fa=kEzOB=gNqR1h14L!_Tzed;pLk$S93Afb!wj"
        "aQAIBFkdOx-*5R9fU`e8nqO@l@P&>UB=wwhOb=Y|_hMdm|Q%(C5jLgtgl)bCP0JesS#k%~sL3mQ$d8(w|DYmX#Uy;u)KBi)o"
        "5Mk7bgAU1(4oXrT{8K```&(2o(4Q@z_RBblGxLHiEBN|c2JapPedw3vBg(meMbmqS<VSJ#y@@br`C}}i2<M9mzkSMXW!*0r|"
        "tdW)0zeZtwFn2(+TV$N`($g!lrx|UUoHqPSU`+SfxxIr%@_|QE8nS4S5UA62Mg|^A!8SP@gsh_3&OzfZN_S|}dQgI|kh7Gk*"
        "p1*sJD6Nxa~%Kp(;Q~g^Ize^yYciey}y|uFNu@x=sfYUo=m9+dE}#g0i_<|kq`HDN<GA*j&V<+)T2D|(Vjx7M|tFfJwmD1I1"
        "?T%A2|5AX4<TuKGGe@J=#%@))NgImT{|YD=sQ}Ovg#b&3o6p;bC~d%~u~b2wT5RPnKP-xnCWk>sAC?XE!x&5o}p;-Y(e~3tt"
        "J_4a$eJ`%sgeX1cmi_QPRulAI%-U(e?6Fq`c;imjU-eK^nT(e%y1ISLZi<vxzW_;ubEw~zEc)w$QLa=d)Q(zV@Fn-#TCct|!"
        "Q?LOI8ICxQ`l#8ZF3H_SF4_&GCSH!5(&AfwC<y>=Fs4=&-WHi%e){Knpz-?f9*f88{=XzzgR39%@G8aqNbZq}ds{<N*0$1IE"
        "jWO+dRJs-RdpqGt3XZiQ6WQ@tKsC>@%mu;{sbnTyMRr@YpVLC=W@1KFYX@--)A28JAFZ)ns|~+VxW6K*TRCVO!=mw`)Eyq_w"
        "b=gz^zxCd#~TzM8S#$s+^pB{JiIf<Et;9=CB}=`^p}_2#qFLKl^umIL?x8k&{z?=01Rk~itK?VBD5KH_Pzd}1by(v4#NFU{i"
        "1u@Uk%$JMm_k9$t3&~#>U?0GB|8d!IgLaBP)G36~~#_9}#(bYS{ZPYi{I?"
    ),
    # pre-#1008 live gate (059e1c7c…, the five #1008 pieces reversed)
    "059e1c7cde6f4948b9fc994a78f5713061e43dc49a30f828f200949b73716392": (
        "c-pO6?Q+{jvi+~8n9FRH$rZ^+vg5>b`Q9kD9IMu$vX;EwT*pO0#85;80$dCrg`3K|?>XHw;E<MNXLsc)ivoe3p6=79KL%+wo"
        "0-AjGOJDU<u6Hfow><nQrqEjWiGZZ><k8jkM7#p-QE58&TqdpgGb-&_rEc_{PplF^X<1g<_lv?nWrXMF01l7$(@-dRh3y>Dd"
        "dY^n)K2xYyoA8)YxlVtxRQSS)msTYg68=lH7D|7l~P9msL_{WijOC!GG;%$4uTFpZ;ZJ(rjA4cXib_b+gQ^ehmM8_+Xxy-*$"
        "GP4_0rAtD?Lq236*+27Z?pIV_UY)4Az>Zx>mSJ#gl)2c~NBthnr(gS~^tgZ;h1!@b_noXxGXLD<pp_pi>(JQ3@3lBO;@2G3Z"
        "N73MwvEXu`dSZB6!AH-hc6H}EpW^OAxGWFc9%nd#Uakya0B43$gN^3b>NNT82n47Ggo1(lZQ+(;JVBwp2mRos(4mDZrY(9gt"
        "^4vw@7TE7JPn^qU@S$k$w`FE!HMP!rFuu#LZt4<Sa#x*xkjD+w+&=f<Oj22B0R>%ME?Zrp)T}BOa70yb8I=#cY>_5a5LMYE?"
        "VClC<^E$))=<XTq=FZ?kgJor0s7{4dIfVr8JIYrlAuh7trrqJlQ}Vl0|;#~6@wV~+0gjvlO*R-E0Zmjd4|OhD1LFQ7i2+?In"
        "|!dlj2fta%FolDOP}VWo=>HoF)i&)n%HjMr#nX7E?=BN#<}@QL5hN9Zdy=b33a|ITOXj9jRKJ-zC|CuBiFtrZ^XXFi)Jhsj?"
        "ayHYxXtyW#&}m+%yQ4p#s`C9ELJ(P{H!X}QpOUIK%YWSLF!Y?0OHVh`AlUye`C1gv;8h+8(*vUGqiHeX+q^+29-K7fLeFSBd"
        "xn3P4ZsK^A~nU?r~D?!>#*??3otV!{hnU<-A$!U+*ho@(v@J&|G4Z!<!9-g{LrdPnzm%vOdgf?L~Pj1R8b)>}^faL`3a2S+$"
        "dHe>_5R{Z$Gv50WQX7GX|0)55>wBoHmq3E0+_B7)sj{4Wh1IUyXf5(V8+b?K7kn@Ual>}F9~el?kI%6QSk9=W0B|6iK4gG%L"
        "EI%97K3MXkj7hpK-0a|-~<3HEfL8b*j|6l4OooOmspMW>XL<U6r{~PTsk2{Cp1B4WV)S|b)CNH<R!l12eFM=l}**gGj&F6IB"
        "f1|8x0{`us~LKdY(Tzmf`+c(uEh+lJUDLo6EU=DL|i2%ciKGGTc)a#b>&$#CmyQn29pXtqSN@*6W~z^oi|}Vb?3n%Z0sre+X"
        "=)DBcFRUuRQY3!A7-v*cRs1`AsgUStJ6lU2fp78?d^Mahr%XK&m`tCtNB(-bK`&#XR49eA^uAy=ygQ{wU|FuH6m@@y(mpdi1"
        "~oXh0W-n*RoQ&So-e`#f@KoA8Wm_GGf1PH?lqMH~S`8P?^$~qs4Tdcg+0!7ihx%dn{{Kme|>Q~K$Ns~I+1`mjl=6Cm_C@sM}"
        "6<}1+e-oy@+rcC`k&Guds-Nqms%^RfD!C?T0##ln3>nwvE@lfZZG7aGW$wPL>@vwJaP_sFcpd}=E`|5HQK_QLbXcTSnMpkt#"
        "9TC4p4tjF2F7F!rAoDtn?u8k1k6F+S*QD_sx!#AMve)xmX(Dq6;zA9@kA*VNe#nux8#^Mb3x>0se#OELP;=d94;Z#=eG8!7w"
        "woHH1o5Bd0sC0B#R8GVV@lA_4oJ8?vqDf_xHb%B33+wb!_2EC^%Ult>kWE3)1wh?kdUDidNhMI98%Np|F-?M2?w(TwROfh^7"
        ")21SP||Z!BvPsoE%WVH4L-!nAZXjD~EiIH0HV<N{K=XH`?rXHEXsLj#uqJYNmJp)np0pO|HdC)R8<OBPwa>YE>ac>Nao0_^}"
        "QN{rsqH90vc3Gy;Y{XW7sxlOJ;3;g(;g;yvFP%N@ogSDq%C{Ke@zM;4=bQxTaWY!eef6E(8Xuz&)HQ?3(qBNkm&nHt~4vPM;"
        "b_Di9#I`u^%rXJXq$+cZl)JjmZxri7;#BvLO%s=;Qc|%ttyt_OQg-BaK#BcLb*Vwsc!cr~vY#)@+HF5T1ZYiEh?VZJPQTr0C"
        "TV{=X{fh+hN%`PW&hEjh~d)x_9iKy!5sjelxPkfgGLp7R~4;4g%J3?#Em=zGxWJKN(#3DO;*%fxpF0i#-@9y^j*&ReaGw!CU"
        "3`o8K1lxOXG#Us*Ak3$+$ZMv;D)|Yt~V(JmKj9L6cP#4e2s?Sqq^cthclK#YoF#I)iY6F;<Q>Qn98QGL`SFe8TjEGc;{Kr(K"
        "W8gKO73X(TW6F?zRPk%#}KlI%wv51SqKYokay3?%Yc>#8<*4DmfBdy3^-?FN)SO$r(UY=*swr+lG}FElJgT=3Z-EKiVHRz)a"
        "g>nzV{0<$8^v;;G67D?foCEt^yAYO?)v09sUne&I{WPH@NN`1x8#mbyZ6%AXQ%hKo2mPw8m=rgaK`T-`rNfb2NUCCC!)$C0C"
        "PSYwwgOh*^YE+qT$InsJpB}$FK6){Eclc&}JpNt~^!AqKa}Wb$X%Q(!m^qLPjBl}S`{_sqfi;6A38S6ePb1gdreP1L$G_ChO"
        "t4N@bsTZH&@+SomGQ&Kvsb4ha7A~uw4{@nYSDJC{9HJ8{pjJVvbfAwL(O9kWft?~@#Fsf*KHa@y|=WJ@+$PVG9G}TIHEyFWi"
        "$$UQE8&8q?oeF6EuT#5Y$$sq;{G)a*Uq<;5#o6utqQ@=Iybd@aXS9zCJu2%TnPXw6D?{p;RkW+%FBDw}rH<#4kH(L77%_3{V"
        "(XP(JdDWYYeEl|VurQ!_nUr_ySjN!ZXNMv{<ei#lKV+Cb_l+5@RgDRoH4QpWijLFZiSC7L$7W(n!f$i3Irw^J=yoU1d>hvqa"
        "xFsQgK*4Sc<&=?ZpiRzZ*Tg0HGpwd2KhM*8t=|<eAh^(Y`h;b<+2$d!K@AW0r&Tr-`+3l^7H3&T`=`4;^;Rltbges$qyV=H<"
        "URbi<c4BQ4Da7N23Hx;4WpFzLzOs2<Mmeaj`piLm4>a#0i(mC(x)Oa<nCGc;5!&sYxA+$*&XasLBJ%tY%QZ4JiY8Ya`}mSwW"
        ">~bLXIjnQY`U8w;qU|%(y)zQ{Q#$UN3fe-fi8qLhL^VX(a&_;f!qyR>4m46Pt9*TYff5w8FdV$OU&=@?Hw@a_xBzl>c48E9!"
        "0w4Fvk?l;=)#8-~;WwqI2*Ywdz*yW6>YXvuA>$9@Wz?u?JlLpJ$<JlCNYUm6F)_b3rscGw*RfHrx5|K`jUFBE)fZ9bKIdqc!"
        "vDY-uwMNQ`-BLCcg^eeWQ|@b1-5TLBTvyU`jNEYT0+8bL4#OLDTO6Qtvz`A#~E%JV$Sas^f_5EKpFT-%yxN|U0>r_z~a>YJA"
        "9B2dRQM5mwj#R9wNQ<WaesS4LUqu&apm1wwbf0xOMW%zI{h4vmwf=HQ#ZXf2!Xcdqp*9G_nUJ<!>q`=PFvK@~{I8q%xS|joc"
        "bDCrvyh=3uqbX~h50iFL{_9R^nfxQ1s>aFqC3tp*AP^pm1%_Hzs@sq~o(fgr_6EsMT}YP^SpKX4;$i)3yCTEH@+2K--6i$C*"
        "NG}Fn1Lvxu8`<+&7k{_4j%Up4iHX{zW%!Z)m|G;Rp$^~bYtwVcG{?iXIeZz=)ON3{C_g|=icDS<mbW9!w<W?2U=Do)g{<@_~"
        "+iw|M#=|^Phy6ho@0FFp;@_cUFN1Ijk9(lO=^G`Fj=wJargD?WjT+c#dJz$XwcwB2gD)Y@^|TL$XqZ4(zhXq#NdK9%lp78Pi"
        ")Gub|4CCd&*hIVVh4Y>rUatD$Hf#L(n#hp&%cOwNvv-kh=yb#Z0Y5%-6p9i3m&u-G;AYFYAO8QC^~<qAD$o=sPw*kE)>!@_n"
        "DpNFK*-B0Z=s#qn<AYSdSOUMPbg+6Ywf?U$(^*>^cdoAG^?K91BuO(E}C(IExaQ5oRygYt=WZoT*PtD2Sj^4<nvy+q8=Iro0"
        "e9?Vz^m4FwupgZ>?e~!RCZ|7*&t9pb=PGPo=AKj7Sokc8;&>of1}2jxueF)sc+H>5gm4Qpm~y7lK02W4at1tY@&r9|hp6QZu"
        ";#)p%4)?~S7qfoNp!Y?lE=054!+DO{h%f%X&k;h!(N3eGGf5V0gl!dH}jIUZ%zA(+o`e6AwtE(v4ZY_r)ybM3xaE_K$Kdvv_"
        "--L=Z{ea$oVP>A-`B^QNUu*U1gx%6qjKQ2#Xfd(m249N_(=4{XG&kYw_$4`#8hNQqfE+qgBDKQ4y;lfbHMR<I@~=2~^V!W*P"
        "Zf2Be`&V@ZZ*GuJ+(tz-cbV?F>+h|<v^21;7dSv1nzRwq|hhlv{sF@%~z$vPdjB~M+gqVzBWd$r8Q1QPwBl`px?SeDtdn;{e"
        "2q`jrvTMMd^8;X+3sS^-~2>b2#o?a91=>=9Mzx}Sy+Fz%3S(_vI#cnGS>C3C%m9;ofdB(qX*ME_3yKw}0jR-UZ>NO)8nhmqs"
        "E?l=43BShEAeioTZ%Ce5c6&oPAdB~eHQry5->+$z>yKzftm3(()p6J?iJ9B9@*BcUq>Y_j$u9J!q?n1o^YikIv-N0$hC|RRM"
        "QVe0{QUT=J*Ey33e0a4LQ7(A!+hY@K+{9tKx2OHOhy`Lm(zxz3R8k`+R3&Zni7K!a?aX9D53|UGFl>Ff8ARN?v*S;m*AsV&x"
        "$1crMr=UkQ=HrD-!k{jYg-}t=Jq-mqk=6`V-o4EY9N+iNRKd(3Sdt<abxrE;kr^o2`dttnG*#5kFN8NCILyiVd1^X298jp*2"
        "_ZbYBle+oNy5by`DKnjvG#rfE3sul(s|6XbRIgi2ax>hKmpXtx26*5$o*h8L#T{ckbF?p9c1W8Lnpe4+Gk7j5(c;cxTCZ3{$"
        "YoZ^FXoeBC}Sfs1JWV{pAqnkgU6^+r$C>QWKS|^sNNb`^S2anC}!T#RE{=@aGCmi>(w<YfjFh0uC?4tT{v&-=bx@Ye~f-n|G"
        "2k?y-I%5mL!@yCBagQF3c{mi+iJrcs5DN^cGjZCHFdn1z_0+JPbjnGh@6vHQpg)X+t!Kq(CEuNx@!=0gr{?g@k+4ALaBL2rp"
        "B<l!JDvhE7fp)f^%*H{c$656iUwBtjs;r`{4uqot-2~IsaTSo`V)GY9z+7qBakq9IgkL1oDVgQ<T!mlpHRp|b%yYbf-08x$="
        "a$fN1KyrxmaYi)?)5T-aaaI7#&NyyCC#azy3!3w+Wb7P|JKA2hnNTZ`lP6NJ!}08ZtF%-|Lb6d4`RJ=?!{xp}UOuiu(A{#{1"
        "Ocb7+qEoYd_b(nue;Wy&IpjYI~XZc;tT2%+HLl8WE?kvC#YSKJ!6@rUB?ftKKeojE>5ay<Is$1`&>e*Keq_v&c8uHIjq0GGt"
        "1-g-8SWqmfJ?!-|n?GHfeE*!<;J|9wd;b=p-&w<pvIEtlx4y5kIQ7r5pNPXAT+s%i(G{a=-+s|0iN0htOqinS&&McBt=HPl}"
        "y)}XI*u1sP8?B26dCjTqAS8Z$PA)dFrc;OBc_6{CSs95WmzA}l$>#fb5fg?EYGXXce#m>rS68PxC|fs9GKw|dot(Y$Gi9l4<"
        "Zy7^&aB^1@M<59U#vIhXYQ>XvpSCR5Ztk(|0vF*Y&FAWz9nJ8y9LNeIS;K1U(&YD{t#Xbo%kT7^mCfuY*KC9BK9`2S#;yLjH"
        "Xp`8oM4g>+6DHTsHCukJ7oDOP9JaTPurMcBx56^0&Ne${DmqcSmd-PPBQrAr)Sc6+R`WS-M>oFy@mqRYM4n<dw3XAC{7B^U~"
        "Sy)>3ZU)7A0O-_JHCb*eiDhx&?Ynrh3zZVW*aS!uI)<j<rX0X@5?>xl}*drG`*d0Ol3ZY;i0$4z`q^bGbQnm8wq8@F42{L2)"
        "k3nrA~@u~G^0)0IZl)0rp2tsGL(eLg4n?mnC?u;eezUm)(HcSnJ5qmr46Dn^Vi}p5;3!>-mY3VmzvF(ZWmTVU88twcGX}s}n"
    ),
    # 10-30 22:58 live gate (7dff103a…)
    "7dff103ae7f77c69cfc063e74d1115a8dc98bcfc0dbbc6ca4b6fd260f9b826d1": (
        "c-pO7YjfMilKrk<F-vci$t#eN6hC6Ql#OiDu_`v@NOF9=j*A)*LlF@O@L~Wlyea?p?bAI23?RvNwyskZ%Oud#(~r}qdq#0Gp"
        "R3{UGAWh*?hjpDCw6+NOEX$+)J5lmt>JKZ<EgFf?d_XS{`8X?KKNlb`ax~uukRnKpMKg>_mon38Y{h875TMJt(xhgNDO_F@f"
        "Uwo@ugXsjFib@Wv)%JQH7Z&nS7WT6XRi#WM>Pr)M}Yr7P?IGY=n=8|FJ(?YI<^X`pdqGlUe!EmPMq>YLy!K(f{w$Cv~9y+S("
        "?4X!R<)%JOwKEE0P)bi2Gr$s)R(EmZ$!vrMw&zE!{OsiI1g>@re&JA03YyF0`0cLpPMwlLOsVdJBpU!AFiX6y8HRpvcK?--S"
        "2>LdP{<;%^eOiW=vvArh8s>s)BVG6Ua%7xjeHT~$t(FZEe(v8wHSj*A}x+FC+wNA=~%JPdmrZ4RkS$MrjQp0b+p(-h@N$2FO"
        "G_`@aCGB^XYHO1@`H;1D+fwtqm>KIl7(V4zS7lCHvRA#x%fkjrY#)2DN*9K-AO&riuWDUMsd<qv$q_|{Wkf#dWwKZoUQ}Up9"
        "I2&FQukw)m!ym}x*#uLAzSLQqUc+g*%g_Slpz!Qs6<f4quL9a-bpMQ!%`5MY{mvr<Yxuri%)clr8X*AuF`}SqeO9w(|TSO>9"
        "K&?vxUws`5~LvAL?vFAzc`gDZ79P{8MEf>&<=>1hvJ)l7&tzJ(cC6w|Wm#k;18&mnxsL;_QxCEROGVvV<#2eAyOfeIP8fRqG"
        "-tX~QbUUg>G_zqgBj3qB`TPypp*1zrwLTj-U+Lg#5tF*wz$WSS<+q&#PPkp1xG<oJw(m0tDYR#maeErl;_zP!lGA-`o^0(m1"
        "}CfBrMKo){UL~8QRET<pn6EAI@R|F~-M#c1+n&q(}lfxdb4^Pin;dPS14HWOQg@5Zp&#ow*zN45a8PKLk=jl2xVhdQDQ(#$+"
        "c5)ag@$%?|q)}2ra*2G8IHg*NNB=80AZ+A9UA#mfnDY~>RL=zE_$ylN%I-HJ@7IYpp1i<|F#$K(j-IC&(CY1T+5}lniKQsOD"
        "YD^1BsdnNr+C9`@TBz8@CZeq>fdT`1OQo@GZH&6gQ&p<S`4Ajxf<@(>Lp_oNn5yZ>G>3$!UVm2)$eVL?M14W=JXYQVB4roUK"
        "MpdLubkjOPhOIXM;}{S|BNV1BV|ygLMBU>5L1FWcs_vtILIa$$>tb<yBTbMY_i}$j`W|M6*02%v2EORt4lM<8%-}`pWizu+0"
        "jKd};39A0@Ux6dt2+zfNYd7Hy(b)e39X8_Z0J@B%8}ouptqG_+v~TUPSs{><9mSUs;OVyZ00&vPShLI*so=2WXigBjxTDaGi"
        "jx=525XMqIyo#tHWOY_C$#Gg{q5c8LYm+}CSQ3%FQ9TrgtlNDGuHa68?9mj>SE)_ed+-O0hXi;5!gC1^UKPTm@>O#f3)ZO4A"
        "V1)VYm!l}o33&<%qXPb$qV(M!Ok5Lzc>JLFxzt5z;#N@cXB<rgm6sYRW9!<5YJsJd%iKIq?RSM)>7*d6zBW^bg9L#q#=U+(R"
        "Roz1v$)6;=5t=mMU|wnDaghYW4wkyrP#<WNW%+F$N}7G%KcN(nZUTD8slZH3PZM(pjt-C0VOk%k_?aC0%PjRMIzf&gDS7`lw"
        "e+2`iLrhYDyRNtR2dORDMvH=lKe6f@Cm<eX_R`?e3`UCl4M+yFW0AWlzyMCbKyyI9*a%N$u2RfazP^l>@0ITIm@I$AWc7C^T"
        "{u%TaRzS6jz%08<)-AV*q9%7BwFYlF<C(YAtwS#C=*8dYP719&>s7bLZRR#fF;UZuYtDsmYG&%@CVFvg?N6Sd0ejRuY8dYPn"
        "~NWFRU`W@*@(N2L%6l3tT0Vm6pAkB5`_Tj%tjlOm$@b)=~mnQ{87D3j?+A~5Z2ZK!Ch}<Z+j9gE}tjcKrHEy7wQS9<oecW0K"
        "Q5cZj=ZdMLgRDPUI|%lS#ny4&n<pGB(;`m|mE6sj{06bs7fx{x&{W$bW=aKaT7c|nrX8snLSocb7aA0mi%|Rn=;vrzz3uyy0"
        "m6wgw$dHeiRzsuT=u&~L%iiGOtB;?`>%>f43>`ShnPSUc2M9kMYH5F(x`y%imdi00|LJ1yy2I~3=vi)N?}`}2}a$il^Z4+ZT"
        "CRwyPWfROKlCO?<T)Yj^9tX@uI$}Pj$78xLZTj{e#-8nyeR`aPUA$lN1FEX%q6Y5FsyYu(f?}U+6NNfp8*YY%DlZ)<6xA%5_"
        "$*U^>7Vsk)z&u7~B3Ya5(YT$k}0yqkgK(f^rAMnT7eW(WP+ejuF;#PYy(MH_mJ@_PpKWXspu4IzD|GZ=!<jP}N!azvZHkhEl"
        "R-e*I<Jc87K6%m;&lQe}1)CMS11I(gY>dZAut|uo#ykU84wYu!0=8x3zWL&pOk;Ko%Mx8T@CR?2I(&wZtiX1+G&zyGR2Quke"
        "OVCJn#akh)MrY!78W#yQIGVtqB$oMZ@|;Nh>Cwxh@r&vE!;{I;<Y$hccega3!!STrhB77dGY5cyaxK<ve|lU&$eP}g2&1j-u"
        "Sc%BO~V02J^dG(x$@TOi;nvkE)3N0M;<@yJM`-HI9#c_S{cB}T(qb=SNxn=bp6!B7kPG>ZbnkazUNuYlShxD-N$tqBfhsX)B"
        "MW!w>%yoLt#WiDV4w|)QfTxRp@MnCXb_;K!=jrh?LmO5(|uR69D?o38b*5WYp^25l7+ppKo6u9!+>D{}Q#Y+!_&8%S7BC6}@"
        "jVZdnn(=%hKygv}vA$+#Tl`)-kh+h0N@0->HNQ67yIX{F30jBgSHNmOaGGTk_Cz<dh!pwcFgI)Y;%<GhKWbFB4}nl{s*1ovm"
        "a-fQF9sTwTK#hK?Lb(&Bzh`0`FbP&Tgh6r&jy6Ln73<3%w?FKS<g`i45z&?q{g1JK&mpp<HS-k&2#Hn_^UTk=`w`SJR_pE@k"
        "FjE;HM4A99k23B?8%Mop$*Atc>L!wb#|dNf>Az3N?IiG(Nz**2L6PXQAmF<%b(gC6)gXi`)<=XnoH}Qr{lR%1{~U@7ozC|Wd"
        "2WbhE1nt!lPipU9A)Pj7HsH{R_ZsJ?kdw5o)AMC)!8dQkW-u^&`oa$E*LgOm!@>tk8<22xh+^3__t9{)n8i;CN*9r9s}u|^S"
        "e7cdr11-od=Zl59_Qal5Q}}QCYRTFohrZkoHc|1>qaC>K7kF(Vx`80Y}jQ>dBY12m1WK4m@k(uXrLA1K9BA0?~A!KGO5F+1{"
        "s5VmZPtggAZLWLNLgeuKO+TWXg9&N1gK(lW-Uu6JNyc>n4{Cm}+4YvIs@5|JO*a0COexF$O|p>jM@&$zQF9L|H5OJIcp38G0"
        "iTel`s(wJ1aQaU#%eY3nFfikW^bh>F@D6mg`s=#AD6XCLF>bE?#Vhx-2ccnL=;iE<h>^<TF5u*y-KFs6MDupbt&WEqZ6_$HP"
        "3G6kN?YVd)M~cJun~1!pPIZF8D`&&Ms=So>FkqMHzwD&s$v>r2QCS|pc+bu$2^a@Mfu8F!yY<!MDMJ-KUQzKA7s6!-EO%Bw;"
        ">r5gW&?x?<#9O>-o^ah=>!#*s6dcW7F6g{si3<L_8vuhdz4NO9zTvA?$qg2^bQG&*2?^8W|eq&F68-s|Ks8CfA#R+JHsc_--"
        "o}CK5Y-~3$4<{C86`^AA{fj=Xd*$|7Ktwod$GZ%5(kxydWIJux4K!uOM8fA3+Fk>M$X-1BNhk7=x_gxwIQa5-&*5Mw0^$fl3"
        "8+V3%3K-7p?=aW+)F3B1*F3W~g$UM19$W5RTW=7@;B7z*a09Gd=i`1<I@^z3MSata=5LuS=u_j}S#ou95ic2&7q<#?G#wiSi"
        "thI-I6nQc7TKz4A$f_9L89sxSHzqY@Cv2vB6d^LZrNG`=T!^b+wfF*TZ|2yXRq9q)neWN+PXbBPZ6?6CvoV^;Wmq)M1>iyB="
        "R2}~|KH-nfj*nlfv%_cfMgPV4<#1<jH#le79Z=<)o_?5|y%I&wMc5)w9j2hMa8;DZ@sMMgVp3OWDa{PVYwk?Or<<R_<a3dB<"
        "AAD<8St!1HTBFrL@gd5Yc9<)FE*HU6^1_th|V{p<Wb4JgQGdQ8`Pu#jl-8`v{%N81TkRw07tmRdXa<smas3o9U99V!ZRj}6="
        "V-MT}uKkNLX8VpcK+llZ5-$9it4X=8Ggs`Q=JT0mz`eN(gpi`k1Ui!h(f_8vC$>(hlrGfA2Gz)$!~O`!K^vV%AKU(I!LJC=n"
        "|uK-*t0!qXgd2~g7x=Lztd2c*7B10|z(6I;I|tz<?ZhI&9a!Ab{*7({7VXVyq+TdA*%3=>-lA%&_;z&ak)l&35<L3x-Hdez8"
        "=0uuZ~m@lwR8PM$cdV~Tutsm(R8bO6#LliToo{u=nu)jVJ<TDOF`2fu1ug~(X`EzDgr5f{J=(Ylpj$VBh)WSgJ0RP%<{sp}4"
        "hZ*EFLZDHiUL&JPvr$r-rR@&_;n(yw0ZjjTFapl3`hyW4kcE4qH9lSe->+er>l?7bR&iKT>o}@bh?(28avP$D02^D|TwUNzE"
        "-_OM&u^<U)|C4#81_jo5Gf7b(etCT`k2~hD8+mi5NZ&6=jQ{rCYl`jdKhzaXCTs0x|})%MVJ7Dl}@(q&;%G{kaJcOp#UBj%3"
        "ui}`%Q1faW7!uy9AfTa#qCY&)p3t1V2#3Nv6?vRFa)ex2!#$&a;3jx)WM|ERN$6&cRv*-<7(A#CKQ5tXhcOMeC88NISwu#7{"
        "*7fB>5gV!dXV8DMsxV9gCY9m%0+ee_M?Ix9(5oKVH&O~Y`~U%AuG%FFBH4UyDTYJZEsx7!pRwaW)hg=eJL{!byrb|<ZAWBvZ"
        "Ecp>m`7i<hX;CFH3wgmzjC-H%~&XoFGvPfV4;_*(vN85kCDI0^!C>P{&YMnq+_jYz4qv_k*dGaWFxLdQ-hWL&XH*hg^9lGT5"
        "=)K7<!yz}tqbo){?L0&4(Um5n7sQksWneZV<*bJp4Hsm@krqyjJ0vo7o|{oy7)Pl(sj@OznsHI&MdPDZ99fC2UI3c>^#T87g"
        "FYHlH))`Oh=Z`zI-ID(=VwR96CzJ%uQ1`|(cQ`Md-dk<0|Uj$yZXy#$1gsp!_!~JFPd9Cp)@zj`E{>zp{Jhe4LX+>x<iFUyH"
        "jljI!WnfyzM!qAK=uZmBhBD7@;&7XrS0L8r+~}Xq}_BGOW0>H;^Y3hpfXjC#=_jt&uNG0&EU4Fx$f<T*kO^GbI%0`I5HMh60"
        "3x_2sCz9&hvUu^Y|M;}lgv^Lwx5VrIfaVZxKcH)C~lN;PWy=Ixm}p1l5`-oF}88WR2Dcznu!mq*V+u^q-7kYy}!>h4}}6rKk"
        ";kC4ZFiBO?sLIF_>TXC*(K828}gd++6CaN5Yt66izht|_szFa1yylSubURmB8Gu+1STgv%)Zq#D-ov5e_8DbOekoMUu$s?gO"
        "_+9Sd@I0`-vBmrIwNpNolPK9`Q+~Rk=SXW}g&If@j?}ZN?DhbBcLg=gb%CLz8%fY<6*^slRZAUnGRo0$XAtBP=hkj(zkyo5Z"
        "B!F^#zO~bSv%IG`5&A|O>*;Qc`~6d3uAn*i)(Ss1ifx#T2m^tCC)pJ<ebX9s_9>NBC4Jp6W9&w=j4p8i%o&rhm#l0=G^GJwq"
        "ru{V+_Aao6IG;?adiXfxbN<T2#eyaOiF6E+vLn?Dztj>T|Aza_00gE-NU1#7`)Z;_Ntc%(8a&Cx1h8>XH=F&pYNXJDu9#E_|"
        "8f!O(~gMVpzg+}iU~t9=*Y0l?Y?H;Zk1Wb@>b!9oy~uY6(@EZN;-8~cN0oG~!b%96~1WSqp^Y(dWJI2J>2Ao0zvfty*<zh`M"
        "~jlVpUn);A)GXCe;EisPyo!k_SV`2ViiYRFUE44Ws{!Hsh%)u9$kDx$*foXN+3FZ3I;;u>^ki8I17+1Ug>8^7=cc(%12?_a>"
        "dS+@$frGib4+ujE{=kMhxS)Fct#|#L&F^>cRh2sjiG%il{co7Kw%VOWOXmKm&bv66^e=%I?BCRSswv}%YV(cpurG2Fr*g9LS"
        "5LOl+gINHy|uRVPb~1cV-80HdCl89eUJ?LtTn5CF5JT1OEZ4@M%B}?4pJ^zc8=gc$IwT{0gG+zNu*4hhU<>q7%<%)Hw1msZ1"
        "8z-V;J$9DR}0<2ageMA2Enw3Mo>A`agW|IC?_V|Iwo-xU>{f|9jLdqU&(Cgx#^6R(#V@uJ>jeMTNIMC@l=%9T8w5+zDmPiU0"
        "CduI?y^W#f(qY(?)^Mmf04%%5W6&|DPMM1-a&194^gvvB9o??BB)GFCVJ_RWvp>G<{d`I$=M$e94Hk783&-x5iW70qP!8p-j"
        "5dU<mEruo%_PVWCd1V(F33?rVRVM)8<ZmiZmMgjFa8Oy!PgZntEp+a(B9iO}ypQvXalv}Ac81cnQDsX;8BqOMgpPG?V!Sg1v"
        "R}j>(A5#%jNo+j+f!o5zJG;^M-Pl0SR!2h5{qDd5mmF}D1eL-Ug*o5PrK-KmGf+Rv$J&7?Pki>i=L+M9T~*BWjHDHM?XF>Rq"
        "|_IsE~>KR8+?pmtz#b^c+15C+B!;|yCC9gpv0j3A_<PI1E-unW%3e;vuk5kO6Ct`eJCwg9o*Rw_ejVOT%c?90KqAJKO_m#{O"
        "zkA-^Xwl5_GUdOq!NZt3@-Y%LUOy;$0<KjB^243dB&YDjCe;p+fHR^&FFQiP>f>l%w1ZhSo(3#@i@`?a6T?Uz0qS%(K%ZJC8"
        "c_XU!}?F4I#B;3jE_Z^S$<)RQY19H%Pmqvnj=jR$1rBTqVp7`ubpD7;VTFK9MrBkcKBkInZwV)buR<n`?-^=N14F8*H@S`J^"
        "ug&ffIIHOxX%iE%46EoqPa+!SK$7MVI;4(9W<kYS|b%tN+geMwp8e72dw9vb^a@&RI%*>wyHouj?C$_y^>3(}?aa|g<xH>z|"
        "$1>Tf9nQRInffs^rq~#D9=XN%xUE^_Ae;N`IN(sD#*Bi5__Fu`+WGBwh(F()=9|NOdhKRDtvj>z?@l1_hS<zdv}Dp5B-2!s2"
        "1-$(T=jb`ERAH!)g~J5jbQB8VHG!tAFo6Xuv7kJm;*IWb6xhGr~z6X(r$$R^*c<$@rM4{W+k(zNd2bMN`4-EZJnLbPKQiMRv"
        "qA%jrz@_gB!Fd5c8vZ>$b&2-1dRmy(vMy`;or8<<0nGugQH}>2S}7Ao+f=sRv3IhTAg!tuVP>Ds5QQz5itSkP7g(rs6mX<sF"
        "8cqrT|v?!khCq&eSTj`Pw(oVLQUSUxZ!l-K&*f$%cfsCzQxf=lXk9ajGbkEY$_"
    ),
    # 10-30 12:44 live gate (7b14b682…)
    "7b14b682ac6866da2c977786384d15884caf7bfb18e807c2beaf6bd5c809a719": (
        "c-pO7YjYbnvi+`Kfy>+~ldB<DQv8UeQf_3Mj<vC=M3Uq6bzBt00ZBx|8SXs9a8v&8w@)`P1CA)$xwUeYMa`qpXmp=G-2h`do"
        "vMC+W=p02{=3d^Z84td(hQbsb=|tK)9?51JhijCyL<P^AAV5%hu`f-->F^vdU&9I_+dwVqm;^$Sn1_5&u(>6sEN*VYv@YKH-"
        "4|;nOT^Wlu2V{ZcV;cxtZEjE~duBcvvJAlet-FwXm~Xmo`fWxZMAb{p_gm`RT<^hbp#{@<UPPkt(ZYV&tR$@8d^xtp42DC4F"
        "f0D!oawRoc&OanpCRyiUj>x}3~a_eZm^seMqWUk+4WB{rQ!>R|8SaesfW|LtCHpf2a8Fkaa3^v741YOdKj9bJ`KN6|Y**;IY"
        "NpJ}#O4@ztD;v?H@bf)rbrRF9#hpL>LwOY|fFODv#EKSx*PhhQrF6fffNY%=gbCqV-Sxh&J8?x|fZWF_AU_q5F3zJM~v67?+"
        "#4TvPlSCJVozfbz_HJ5gn&lHyxD^baa-*v<qbU_Poyg0>1WHUFb10O~4QW9N7G<`qbtR>ydA6X1$Wsg>@<}g~#ya<+a--u&E"
        "woMC$22QRnZoFtRsjPQr7kP-zPXv)kU2>iGO_ncIAuJjS3%P|wqRov<b)=jut5~9vx4zuO>}~x*2*rHiKW3PP~6}&o|i>>%%"
        "S#VuG1MmRAlu<ovz8Hb7N9f%wYomRGGzkeb_ibZ85QAu5Ce2rJ3lh-oaF)aAKyV%BHM1FGnmE$31NqSc(!iH^mj+5$3v3tK6"
        "0}VHIPp^fax%w~K!ZYfei+4wR7<csMNDTrUj<x=J$g!LeT2abg#?ykdKh{cv-1cFE34uX=IIDqm&=xi3w=yw1u#zg4&Z@<yK"
        "7TbeN-3(g`UHLcDhqYre&OIu|Xfy%W}F}<cHS!~GUu*d6@i%V8`Wm7Bz`TJz<-@4Y58}g^Wlh2e4Xk&!)c$MXG0a%=pV-@V}"
        "v|yyf%hPj`MnMV5CE`8eklF}5`Y&gPC?e<TvPuMk89%X1^h8jOZ_#Ks#bG1zK^=I*(F?p76L6F5=y~!1t$uz^lOW3}u@pHtc"
        "{bJ%0geIbDV{JJ+?HM%9w84@-K_?P1CXUTA~6HgiyCa8!QlEFtKnP=y<m(YX>;c;9Ur1&n4oj0x}CKtI+5xm8QsDMwvAe6Rb"
        "Iz4bf(xSXmUq&H283#0c_dnIsE7tg!@-XXIy9`)9*a1W^=j8jy{=WRazb)+~XpM&$z8bGdv^ASP*8b0&>eZ9R!fRFg+k_Gr~"
        "MunEU5Pfh`b)$H?7p?L@|+NtCKuVyt?CsVU)JKn1*GbH+nM6DGH1CGXD9tcp9MXBBx&mB#oyHS#8Oz{6@vxmq-sz%P%;N0-%"
        "gVkaC0;^g<5bE#+Mv%|@HN=k#z&kPUc0U{+AjE@`^kqeU*ST{B{<zF4gxhY&Iwotjzf=JQ4y8a41+{Avg<*Vvi#k$mO=OJK("
        "`HRncQJfL-<m5&<)^Ci|x80dICj#;KL0RWg=cS1^oQkipHxX3MG(x7Ra~HBjJv2pbmL<jCbF<VoC#=3TV~2wTflJ1{Za`H8n"
        "NHF;&n)w~8aykT#3m;jlaKKj0+nK;Von-fYeEj-PLuABL}voyl5$L)401!Z6sKB5$^j)al9CLM*#cwg%tazMsYa7|i9}WfU7"
        "}2%n9_MYYlrk8nI9D9dA7uxAQ}EuVYYpr71|tmU2=Nm4<7AE-k1$B)?y)E#WcI)Jr!yFW3J=GgotDXs!Iy$2X3vh<=UsYsm+"
        "U0?97Qd$$Tg{NwFnfYOgD12aZ<NOXZ$fCe@6FVKU{ss2I%n-XP0~md43omSr>gb3%_m3b{r$Sm;}m4)l^p5kE+|^Nx$#f{9W"
        "@I(j{c*Vtt#tWHwl(qv0yHOb0k2<CIlL~ERSXVVy&XKC_<rA4JR79%h*WP%&R$5JG)YZ#1Hh|{-B3<;|VE-Z?3ur13{$Ci6U"
        "EJ`!Ik!6v2EOd;OA}?YkmvbgPL_#^LCX)NfP?XCt9f-iv)wskt^r$u&U1ZQC>IXq4DU4X{AM9i<Ig?X6rErgEKZk+^HP&mFM"
        "U2yh@)l(`;6ZK{q!=FKRU!TkQ>ca^JI=|P$o0<30PX55=6<#UUybJfszAXLqi-GhFKA9g3y!wostkkC$3Dr|<J_0D*@*7p&("
        "MHC^ppsSWGmD=TM;x{np8yN;UiCUyj1uQgrbany8msozo&MeK711Gf5&w!4@FQzGBU!b@q&CfDaIy+18g4;WK9O7XK1XP;S0"
        "{($WbhZH7aVC32;H9Cdd$~k%H$)xUkKQE-FZvWP}aNoCvw30=Q+OuSsh6GOx<{v`T(CQRMuTKOPOf10FseJXOn#-e?HPR4;5"
        "ofb-_f>$jvYtvgwUs*GN<s9>NDeB3<zoxl}-evaD9*9BBBqF$p&B}nm1h$}d%Zxm3Q9GduSmD2oc>HtnlPRvvFsjHwY1p_jI"
        "J3j3yLe`(G9pt-|#Wp@NwVW@;d6pnj*PmNAh%G#KmgNDV(uIu$_9+$T)<|B5z&<2Ko9aS?ymCnje}DkF%B-ID14@EY7Nu;Zd"
        "#n@HGque8+wmZ)<w$0}plX%^v?v8T{X>k7L?6iUxJoN%#Ym$ZYnP|>dNL=#eNLVH5}6^w$eg)C*F;g>qRVTpH8z(AO5e9QpL"
        "WzvfBbgz)9CEoh<h*UcuU&c>8th+=(lPTzfc9o5GZJDp2LuZrB#+%$P4T3?0$176|=xhPSXIWlIm&0Hh{yfx#Bpp;~WE3w{)"
        "cO!SZNn8>*z3n&UOBZi+gO{^w#c3Ys3sjL2w*fpjtu%R{*<+R$qh-xClhwtTH!AJUslNOR+ra<w+ykg#NNe$DzdIUpxBD2%9"
        "{rSy@&1ZoYGsR3qQEp+PoC9W+;HSwC|vDIqk4cb3YXQN@=Es4Z`uGi{{3u&^&6%Tzy+Jfie0@loFC+k2aU1@O|X|V8AC=sJM"
        ";bt1=c1poWU{DhEdOLbfb^XQZ%hTbD@w=1r(dp<%_Mo?0`cM7PK|nBc>f4S01Le9b+kQGsBFUQGl5nG)-7kBt+NNQTyq^BWW"
        "~#h(x}xJD`ini)|DHRLhYr0u9d_3_(HW#LI~6VJ<`q7t1sZ?ElkzN`CF_CYv4e+b$3A`hINE<wr!gw|mS&vY_!bv;2+2_B(o"
        "#rS7^Rp?A0^l61brU%W&#}wY9mr&GqKFiToaJ)If3NX6pUKEJ!LN({`2S8C#NGG%D<!t%0UUKT1!RT?-jjoQtn#8f6+{1FOz"
        "}}0oq|+6laHS5bKx{K&YciAyy)-l(wYt1UisJnKmtxwJQ&}q=G#twF#sSu&|JE)p*bq#(JrVt2HRWEgE3&t?{JIgT<9B=G8!"
        "5SPBLa*FudJV))(=TwIH8I%xrefPzT7gA86FsL~CvPdt)Y=Z0T$7gA*L{Cg3H+SO{l=GktItiEqs0nWlmWqc560;t^0ydP~`"
        "^+iKQbu*^!BQfweVT?XqUlqJENs<LQC~9c1tC}c_-}FMbVtquI!>KD4+U;G{{?D#B*U9t{p6B}5Ma7Ndpm~kXuP-dn#&(n(J"
        "}&tieYYyr=${fp8r0D%A81kBLZG3xCb(eO7|cxRq95tFLvlA@rRU#9K2?A2G?>(^GVvHlmzaP02r<9E_mG1AQ62PDrW>?#Ra"
        "z~sP3~L1q`cE}PVfe$y7`At@<(-i%udvUc5;)ZK-d54*pnu{#Xad5xQ3r=IMcEEK+n@$J0Cxa;Rw3m;dHeLuFl8926&~ryqN"
        "_!#N1kumT|(R2D<>`!n;@RTk#OeTM30GkcfQ4mK_*)#VOgL31#Dfdd9tl+`&9px%gEm5S4a1E9&NiWHjbfE|X3TGT$U?IG{9"
        "a;he7D9}4UiMj|-QCL&zs+&iq96>HekMoYa03m-I6VDACvhZsp{dpn<NX!2M<o%dc3D=hb(4A^Nb+i~tl3n>eJ*f``j>Oxy="
        "y>Kx6tIA5*Ap+_W`<I!Ny!S`Zlvf4U{eESq6ax%{p+HY{ncVv1al}YPk5`oYWC^ika4ff5NaD%*w`L813FUD%5ZWdE7SRbRE"
        "|7pAqs%GKCz3$-AMQVm4h|@s9zJ;zJ=&|oDes&R6s?r`!%U>>0&)-T{Gj{cr2oIV|L?v2)A4Wp-v%Fddk=(F>3l}uJosDhxB"
        "vOA_}hOoE)OmOHZbO$z3wz87(~1FP@OFyTqhsE2e9urBDDj8(034nsNtO{w;4gSz@m{x3vdEZ%BcXGrI!0)c+B}(Uv)-Ut&U"
        "Sr<W2O_mO4Sne}me{w+z@k6hq@*PhOwC7+;<a&o4kji;!4#c=<hNr@~KH;JT_@FEhN%n>H1><(f*+#7@?pYalwfUO_cTp9et"
        "B-7n2AAgr8ZC|=DUOOi{z&G50Z+-IuO`d=}}XD#6n?JLdkSxbnhFPOtm;PTZ_y*zzARPRnl7wYWS;W=NrJUe@>E>E7(jqZ!#"
        "%l_WMez4QL-=oAgzIZ>nd?kuriLiN=I7~rZ;gTqE<39T``J}FrQfe7A*xjzI4>#Y1&88yl&K7kSyFimF(Nr>b;I(*wthq3YE"
        "MKGBog2Om5S^|`$<vZc2gh<U*Q!kb8YeF=X|BG3!vKae1WYYf^9<CtgnfD0p|P|fJYhmtLFRz{bsJDYbn`q=3TLS~!h^zXr1"
        "mN0izEv9#Zou{xL|Q(33g+;Ox8%&;XuNSy<0+Q2X^6lA2OQN{_M8<(ZaE@^ck5Lty2_@;;|9}G=1L`6?rHUpk~pRelc&6_#z"
        "FAjNY|H{gPCYDS;UB0pSEI9c*I~qh+00Bgt)Ox5{?HhC&FTDiyGf2Q}j<^L3COri5NKvLS&4e+cm%`HrZXt_DbO<NA?quMw2"
        "%6+|&{>UfW%2>bI>Pp+}^$ptWzKR?O4=8uV4mTJhqP;3Pv9lQD@sD*yYG5*?Z{sP{1!w7O3!O<vCZxPX?*}#@&QFMEO@LPJD"
        "0H%A}8vtjP-QIw=$iq3&7$0tc@3*kb?HyQQt2ivFbsSVn_{=t~+=S>Mz{bulXBVs{r<gIj=hx+#!jy*_Fzka~AX4hP)90s`^"
        "+6RMq2%*zK&V0Nt#1!(4Kz9S;bF|}JOPpVQsmSjD8d9F3Mpjk0!@HH`Z$+05endep$wMrzTcEq?Dql|zDRIUEW5?cJ_`o~Ka"
        "j^Z)hIhEiB6|my17A>r2$oRXEgl57;Knw4Av_6qSOT>?%f!(+(7I$S`XAnsu4aUawHl61lV*C>or5m0IdTBYp$`<ksOPt55J"
        "JRPD+v$TgsR`X&6q*D|f!3^76WPLnJks+Mgrx)i$|Dz2v<n!!uIs{-=;)w-wejv2J%OUI;wg2OB*P_-)+SHb6k*#6Qs18B>`"
        "{7U{|_?(PJ9bo1w{qA@s*c1>$er4wlC!QTEJioS!rr;npY`!!2#i0{z4ev7H|(2UcgUrk;z9CIOmbjgUDotG#*+R~)+;&+sY"
        "`Jy!=>8yhm4JTyykrqyjQ)JR~o|?g?F!oY)j!mqE8RmJGH*2)vM}_!SCjd>peayd#po~V-P3mVLVlOPUPDbkF`Q_=^h{)6BD"
        ">Qhyb9a9BPQ5vK&p>hhw!Zo7?8SR^a`DsfMRSfXl;%1)zZ|rV^wmwhUhDW$yQeVUtW=wRjxAk_ce73D`!{uG#TFY)j8K~NGm"
        "z{V4en4gl+MwnGOW0>H;^Y3hp59rM~v5kt$|NW0&EU4(Aq;IT)Mb&HZ2tB`I0WA3<U@W<I7=@y1UH>NL*)z9w)B~ir;TGmYA"
        "7vUzqUd<jqi>UQmu2zWMo5osC|<SMOd8M-7R7aW=f*b(cpkL$NK!9FS!Uap6v1u@_ziF%OqVdx=nC!-N8&=(S>7<!THeV{u0"
        "k{#8^t6j!t6h>xv|C)r|QOL?`p;gh9Vv&*oJ-)|`A+quyOvu}Atoyg#uSPr-4y`U8drD5IWBp$Z|>oc1?Kc740s%%8bESvPx"
        "c0EU0Z6VY^oN%C?Rb{&d;7wiRG*<<NlI{dSt5j%J359I_TYq?@)d+Hdv$fhfY@n9U8`eag@z6n9y6J0D{P(V+Cb)UB+?mj`+"
        "!$Z$;$UpkK(7m#jV=|+5`Q2;NX~`ytD5?S8=~sj8G&8DeonUN+SnAReKLB{OwM(_Ydcz^A49CGl*yc;H&=54Q=o3QM2jkSB*"
        "EL#9ZL=m+42!o)#X?V<xJ@^pZoBKd<Z2HY#pbLS=NjF(Vx*CyC8-1tCso8R;AXv4_`)E&@|#b(Wd1q=XQP9>d<+30I<cJi^W"
        "ZQq*FU%un<J$L*M8GOLTYG#(rNJTMSIJQky!EjBVVG7R0=cV=)9f5})ntxt=BcJxQ{{_~V0#srNWX!+&0G@p1I;<g9oc3-d="
        "&L_rf+X_Ld@XIyt;jz3d;1PS^xOsg$VDA(r(cUkI~>;-Q^yV})H_igjJBMqucNXVPi6H`+P?91K1KNw2z`!!U-1=-^-z3cmI"
        "e!jggs@&Q~>}@vK|AL8YtKDlfJM~Ys-o?J8e+j(c@UGTlO%YF2n~&0kb&-=emW`D^J2H*Vq4M_ctaL$tVt`LAb2u8vV{WhXK"
        "{DvtMz8w0a0_=b)%flkWlzUCNIAP`?ZEM|w6d%>ckawdq>P(_>z>&dFx?Ip1YOds_o;WM8S$&hx#z(9ju8$YF^HiHDN=;`KY"
        "F+qJtgY@`0-PmSqiEDH&iU5>Tur^aJzC^@mXg%;GeD)CEj|UG&g*7M1X~GCzLfM{>z6s+pQp$jUyhg6}?{>e?ToYe~5)cbCF"
        "XM5gH>6#Fgnz!kI(AV>KB_TitXw4}NqmhOdXuFO`iWX96sJ6q}OjmPl%>Xd=DWNVX@`%k#50&6kf_vH$-N7_BrhjCjna?%Lw"
        "+jJCOr0_u4_l#|!T53pB5iR6JgJAW}eSI^!nH&UlJ;G@-);CzcnT2LQ8HZ7-|`%Pr8z^P;3rXr{k-+01b$2xejw;z4m_6^i*"
        "wI_7kw}<99<A8%C$P_*)O!<Vq!STWr)UV)O?Ld?#J_p}&hH=EM%BOll(sI3W2eH{x>T^<ZvaxU&wz2KQ4R1MDKvPGmbLT^R4"
        "iq1huaaTcI#`seBPK6_xMF3@Qc3@ztoNklq=VZ#;u;C@f%9`4H9)XQ-wjEE6n}@R!^bh)c?2Cy5uK(5)Y_mKRONzbBJgf(8e"
        "?AomI5(U%Ssxvcqo^nd>zLmU0`l97K%|W2Se+k1mkIx!uDjlkq=5=N#qq{n_fjN`m<sdAYZ4U62NuRtS`hoF4UbX7#zDQyhh"
        "CyyK4_f&qtng3^8^aw^4YU&>zum_C|Q+H)?D?))A|Jn>?!zPpQXyefQO$S*~UCRhEz)+Q=zs)lIWaQ8I~%@J%^K+VkzQJ->0"
        "88bWd^*N>dx7us@1W0S__Fgy+P_GdZlLUd;0_W_&lCGn1JXJ4w{4oX}XMjKq67tZ@K*=p0BdD7DLV`fagF=#!q#rQa^nP(uI"
        "hns%Du119!ISKJ)SqEt6r{5y}{M`vYkIuW-uIICHYQFyV6dbRQ$@E1_CY?brjYVmo6eY@Kx3htzk#xB>iH3V4X#2HT#a-gZB"
        "hdmBWBxkav6?2CF1t=t52X%iH^6`07L#zip?kSrN-ru>zv`rt&%G~=vp3jlktvC)V|?AP+dSI4Lz@CI-@CWA4JP7tkJbKN33"
        "Bgyy0_)c_(P|OeH`g<&xauSZoaM?O4o+VGX7quoGz6zENUNrDtMC$@VBDmI0)sPgq)-Ps)suU3l5TGe0(|1N)K_m5SGRAn=|"
        "SG+|}QY49=1b+B-wexg=lLZuNigJ39a"
    ),
    # 2026-10-19 install gate (fba83b80…)
    "fba83b80597d170651c3539b93daea1d50d7c8254363df985b84f0feac3cdd36": (
        "c-qx{dvn`Hw&(x)6ur<^nH+(PB){panPDV4){QJVk{nOgagh)SN{C2+1AtaIseJc6&+Y~Y%5suhTkBhQVv}H_AE(dz{LUnqP"
        "EDtCos=f}=9eh{oD{?BsEoUdmAR^Yu+`~w)}Gqh+1Xit@}K`So&9Iw-oDv^|2%$X{`t=>V@$`S*;O`KnJ6vp;=C|d@ifb0Q{"
        "KS;C-XR4md5+j`Ma6KX%bIDGs~{8<B194Ul&OpPXZnde>aKB=qf5=Gmg?UD`7~JE#ed&j$lo*+4^W(=JE!<n?*%wvNSgHs4Q"
        "VJUDG!>e;5_M#W4zVcN3=u_U0;&quatHg~3-u^jv6)%p}t-cpg5VXOrd3PGSPzl!f^vyTV`R@pM_lg~=nBaE{}r<}Ui2q}TY"
        "{^tyom<k|B2rn|MXwR3uAE|1?1&du?KIXdruI5lUdFtx+}`B7;4r$_R4^Wn|e#lV~oet18)xHND27v}Zx>G8#z!I3!`^nV;&"
        "Z0)pggR;9c&L6?smot20HZ}XZ`_DRiyPf?PJrg8T+(tNrNfsCBqtc`?>|L4RMn-fhW|qv8a%*Rj;nz3O=NPvwXm`zNW{Pnh!"
        "yb*ZWeN+9U<2|A40V^n8Lwbh^0)`Pn84QHhUD?TmoaR6Qf%!MWdf&j7bPWcM9ja<rc<Ph{$i15@TMr8n4>sd(O=TcjAz;Swr"
        "f7%8Ns&GAX__E@cIc%J1J-&*_0j=)(srqgike(k^)z!FT=OPR7MfKEt(C53Wr5J&eBOSqSuy41x1-HiV${X9Km7Y*6_GD@oZ"
        "v%icS0(&K4KOB(jL}c~TTfmWDKlk`j$0Th8=^Bw%Low8UM9Y2_<}7a`i(3083tbb(xBlV^9Zd*dvh6ugvqHjmTNv_`mwcrt|"
        "jPiCVwzYGXWmqdFK-NxzGPL|GA_Au=35vjvvir_{d^+yZ*ifI;hG&PG^1pj-7uMUAaV3}JxJQciTc<3-qo|LX8U#0~S^W~cX"
        "Q!A6C`EY#s#vET>=n;kH^z4#91+qSSe|mXz1{B|NBno79mX2dMq{>2JR!ctYA_5Y9w%g$&GuL@Ej)6)GvxtfUdB+IWH-TBT+"
        "M`DWPCc4*h^~PL#S7TMA#;@>&|5xP#-lc{g#4CA$9;b!T;~z&()P<|Px&&%;nvP=yeNqer1mDj-Vr6hC8zy?+XG~*<b1u1@+"
        "d9kiZL5BPj+8+%`x1tq@Yt+6tQeH{BshI6GugK0}?#=Ne<%zODdVlc`dl_a5?dlt(|v=A@V@{R)_`v3Kwu0^9e_=Inz9w3kQ"
        "qFaCR{)j_(*9AN*jNEpxgp1@aD`qu4`wtjwjgh>{%tg7f~IjN{NJMcl6yd;+hATad?Xp>|kQ?QofO)5?<Eat*qzh92P+PG@j"
        "BcS(6O$)mf%UTZoL_y;hJJeEz4u4XY^Qy`34hBGYOTHwyYi4=O-Wi$B%%4|8lA^MKzU2_q`S-yLBe)ePkWOzFGad18y{OjHE"
        "`QW0vWr6_Y(iU&&a5!C-OCYMDN#=_zhXtWzh)Ouh0-oBDPk~TxX35o-KJ`nHrS>0LVgH)P_OHdiXRud~Nyt8X8on?)FJ6Xw&"
        "!3Z!wUa{`a`yhx92nT8sBC3LH%>n%d6sss<Fd6yGBNn?{`rr`7sL9mf{?!-j;GhHAX=7Ln$1^1Xo5|g629AevD<F9x6He<la"
        "t}a;PCA9=mK89+ueVPw6tvwBg?%&K;p&ci{<!qjFY|dPDW@4t_x7Lqc<F_B{cWLUR&=5GoN@?#9i~QMv10{#Ph@XH)Z^53G!"
        "+ZhkD*PS_WLaxB+^Z7$8z0?%;}keie;x19(9mUnd2q2|VQDCZn5TnJg1_I>Disy7@u;`Eo&Yn839M-c%wx7z6j8XP}JuOD)P"
        "MFPR9DeU%vwHcir`xH0`pbNL1of_H~K{Aj|XBNql5UCDBa<T}MKfLp_EML@uJz|Mj2fk$OIPYn($jmIQ%qiIPTMs6eOE+z&h"
        "K;nWfi7G2N$GxYWd6F(cLfpaovpXDa`|<M^=9>6WO!EMlkfae#2#y*RDw47#t6K}yfo`JN6fW{gRUXp7vMG*M-ed*77as#@b"
        "L;H{DkHQ#$WgCR9ML5MmK&90RGYSO096W*vQWN;xDAVCzJMWx#_oU(t~x|&9XtzoU<T*P9FSgm7Zq}d<0ZTe-_te0>nw*`qY"
        "BY92bmMl{CM33Fd^JHT4)BZOOcbKkRVFEi?2)(NBQ_BB(_TmPnOM4o@Qk-O~%X@K+lDz@C-v%y5JL>_U8-<_$tcVI2;laU!H"
        "irAoh>@hM&g2!kT6)%Ls82ux-HkNRt2-e+zp%iST5zWf9V7!t-is;w^AMW_lt|+}YMCLAM`;MG6~J&|L5*s3yaZDA8rJ6POe"
        "0?M0cB>MNE5U(y2Y4!K711>Ye29OXHwNH_8Lw$-MY^Ftjv5InwanayV?GiNY|f((w5XbX0mCr4XOY)1bryaN?hW+14=&SrQc"
        "mx~2RTU2GXfg7T58>(Derg>bV*1%k2NE|@9#L%)y_!xe<wn!dOZl0{se8r#o=C~tJwbBH*Mj+DsdP%|`mUqWrr@qP3BMB|1Q"
        "wUMvSgPqF+eCdnA@w?8Vkly?wBQA*{m70X4~dFflC<#Y1c)8TiEhEw3OAhhcS^s6Pck5KVn)CQkV)ZZ1*>ajHzXbgM1(9eUC"
        "yuI1t`H&9B!H3rZ_D;#I9P8LwGMxMhTa!RGtK<uoR<C>^Hq8KI@5brFdbG0XNY)ak36f&h5w~8#5K_4Y)`^Q}xU%Pc38(C1O"
        "LVVjsaiELk<<>!daf>=;@#HH(H7_q!anEl%}nqLK;|uPISvaVRUm@lfd_1Bhup!^y&Ut$S7Jwx>(uAa!jSv}zI<Ma6{kR85&"
        "<ieeX;A1F~7Z#c;})Gm=<uq{H2Cgrn1^BXxEt`6sbn+dv@DzjqVcSK2qEv4~De^8x}7}&aYK(;O%TC*mHDpQ{Q2Y5K>NxyCF"
        "kfP+>eN=-QZa;q9c>h6};xVe%9Y6lPjhYdd*73AL!h9clrk}3b=(spr;J>5UN7Cg!^<=;xcmsPw>g<SrGD7v;TDGk4qA6OS0"
        "RjIwg?;V$H<Q$S91Op44i36GG%yLgj?f(*Pjm$rbc{C#4~d05-TnEpD0wWpfA|wPwE$-lSbIi3keQJ&8uWZ~ST8z$BBNzM0&"
        "o+=w4F?ZUzir$)El55<P(z!cIqx$&L&JhbF{YTZlECx8XB5gJf6^xxT3~LV_h>6sWQ@K%A(lTW)IOT-<0IBkf6~BLjgmqP&^"
        "<=fc`d<rGx4o+B$rJieZwDoC=Dg0o8y}euJVZ^Eid?H^OzZsZIL{(<$r`qOpB;dh(O`(ErICpP~Z^KN|e2e|Tx&|Buh$vm-p"
        "Qb)Lw)&`m|fGw}Njx1>WP14Ivp3#_`c7Ybu1mdsZbbt!v&V7!3!nY$b*YaF4S3*-q$iV8lg5bRe_h2S4J1lf*0n>QUEExC_J"
        "v%6#j^OwV%#9&{6=3U0bJ;5kL<t*i)mMI!wWE_&jN;|x8*&)!`f$0FfFz=uZbACoA3uRs@-2DjoAMsgI<A@~Yp!8<>9M;9dP"
        "NQT-W;S|Qywl}jK=X_i)+dH!=`LAERFa7q3BNcPA%|6+NStag6CNug6BeX>&uKNZ3S#JmkxP$G2D(;wErD^wvuTKz6OIt24g"
        "5f^A})6cLI!@4S-QJ8K0O@xVvkG}p+1pZkHB{6Umg$ON%r}uX9&JHIetAr!?P=#C{Acc;5OVVHq{@3_s#QISq~kLM$Qbpr?5"
        "p6^B+)rnL>ok02>E_h$lulP@`z&p{nxrj|)*6>(7c&)<twMoY@c^c{mOpBDu!JbtEUs>t=V3vp-3T6DNr$31~ZXE5!|il69l"
        "UCKbl(Nn;!g8NwqckdZ{=vYe?y#R@VN94nD+_=oQN0kR?yh;5ThJzW*AAx)NKx{eY5I*u2m8PI=Fin;;$u-AMf%F5|WmV;A%"
        "`DX4%uUsEUg}HYiux(C|Ux6Lsr1yuLm?_=5xKMxQI}FR@Gf!Beqql($$zHn=j64!%sQN}h1luCvI)@MOPLnKB{lI)vJGr);L"
        "EoIdKRKx%>pX^+ngGsQX4ol`iC!MIfMEic`BK!jX_h-qQ6sfixK7|$C=PL!%!fdGib^7f1aAnM(X8w>-8sXoA=DSYj_?>dBo"
        "09G=R|AXUNWQRktEU(dQ^>Do56DKA|@tQL(tuT`UYH^t{JdjgN_L&od_=&XY&Pli)eRgsCS3zJFU50#citB(aCH4m8ct_>dx"
        "Z&lkBF>V>sAk60u6C?BNmHApV?Kc~-SYe5QF;I!~9*D3LGp?Q(Nf#)%3LttbLUYe#KTA|8%LL0q#+NVJ7MY;`P)|3#t&tWad"
        "R#0ydv#{>QlU0V-2xm|JiB>l`LtE2gQ_=IqT1KbR9ZU+2GK>Pv)aZyIVr|~L=W|EA{Hs4?P_eXv9lN-+`IT*ENhxNa>XK*)C"
        "{f~QVWvEZ>hq5jrc+obd)rq3x3$^>T->e%JZGE_DH@#nV@qd72|CjiX{r6R;+`3#X;z6Ega5sNM9f$tj-nanECu>r0+*9{<_"
        "fR~QI9=eJpo%%hc|kHn4189&*;Mq{C=itRFol)kbv}<-|3e*n4yr`sU1T~OfqtHpC{K|eMYB7+4nXlC{BXkd0qTu>x7G~<jK"
        "pB%m?PW?3+;mL2uGJ9^GJU5s1{`+ox*D3a%FAA%~MQTb&W)omx}4nE=`&gS^sqUbB?=<bGI>u2I@-5I>XiST9}H2&UiTT<&N"
        "25n}}oI?HcXC8ES^_2ImF@<>BDsg1zt~pj~<{p7ea-JEHj5q+PM3=wMx#n7GR%QO-*~>l`#<VKX2G$8k|mJQMBhC@;~*xCM5"
        "Fx*=HJF<Fw9RH7?5zYI0N4*E)0s-U^UQFUsTOf82dHH^&P(Kn#1e<Kf%3`PV&#mOnUpOj+yGoi9V8{g^D5{yGwixrf9Vq?K&"
        "f|df@SeCE+2>CII*%3ozJBqYo6*gtIU=5!J4s^$0#8tKo#CSHRgAclNVIvcuu4K#>GRg&VxWgL*OBgO{57z+qe`U`D_XdZTx"
        "m{7<npY?GHIC=z()Di&O;;qpy(gYst#Led(MKBjObQLIg3QFIB<>z5r)a5Ryp=-G{vy}ZD)vDGu`J@eTsf*m37*Z_zr;6wJd"
        "5x=ETcHSM9ZdcPWtaI#FXiqqru_v1(?@-U4V?xIWBh*rt1fg(U?-(1h3MhgL~%O4;tj}h=u=%lU5$}D3X;X9MQLuQKC+4exl"
        "G+=Lq{k7BDtN?$uaTH~$>odPCeuB5XDl!C&cN|CDUC{`Ui1^6`&sv+*)jmndk?b9faT$(zCXz>6wZE~TnRVY7aO)bPrSaHAi"
        "XR+?}`H&R6c0~(9yIu=Dy^p=bq&%zWYs{N4~A64T~#8Q;bENNHsQEt}#sj`C{*HsM^^EQO|XT%S1XPAFhd=C<pq5Fi#<M<>R"
        "tv$;UWXDJw%|Kp894m_r>lvk=M)Qbo7CC{OT5Cy3m~@tc8eVvr1R9T{-PJRo+z(olIJbq<&f)dqkjBw4DTppPY&R0PEO?yp9"
        "%>#A4pc<Rgn|nq+eu>KMO1|xxn#__Gs^{?pAkO}N*<aBE>AcY1uHo<3-7y^1wi{{y~|3ynk9v)C8uZRL!U1$S#jp_?EN7oO0"
        "`DK=G~}`zM@96pHwHXl)@$xhdtS(oCsIH+GG)roJl-#`ni~C#8!?^O{?4OwnZw6rS1ZA;^A4+1-gQ3V6Jk|L~r84+k|s4OOH"
        "<n@ZS%1FB+3Ank+HQ@S@x0xTtUoa(UF;4%QwcU90UmkTl?Oce7$gvJwDq6j@!qlarF6U=)d+P)ZmFjw;DCL=D8}e9?&MH00@"
        "%n1Nn#Brs<FzFDE#A9>oMg}E4<3=S{NG|3C=8=W9a7W1nn?$zAMfIQPsr!gV@LX*yFT#8ps-g3U?7;TUEHW|shsTeycoce*U"
        "kIQK+OY{&O(DxnC-h{kBjH28)0G5gI@>Vm2%OI?Z9+)5uy1!&e+6w*=n7_dRq%9e!-FBWtyv1M-Ii-FYkgPj!$`U3hwgUf&i"
        "q$|@5NMlx4ft&3%l|U}Xjgt~&d$yH@AbE}yYd??=J$5H9mt%c{2CY6;;jnJ-*ipZf*N<@Ut{<>ZcPI@`aSdd{OqmgQTc!}&H"
        "N@C@H>dXx4=vGG^|tkgKunir!ia};PS2ZW~*#hPZ5vGO~YUP`*%nE%YiqOi@~Ll4OfjKWZ!K(Irv9)=W4U|XWL5ARQ(&xwOw"
        "(3!ECy~rb(}ayJ5D>w&~mOuxNDU4JK}Iw&E-*ie$Rdn?ep04B<vokPKkKO_S?o&Suipvc%ztE21a&4tQDzYy@}|xg;!TmW)v"
        ")zM*Uf$?lD((Q;OjW?q;8Bz(}_GVf2nKRx?!I=nmvUd|4}^-Lv+91MB#!xBscN??K^VAYsBwYT>o+<Rhn9`EgikDp79^7<dy"
        "VEpU(pnnqH`_vGYayj_d<@!TyxX|tD$L`pJLl_#)`uOx{@Go=xnuvPvuj7l$3zPghWR3Fd)X_qVJ_^kkLv3Kw!O$IlXgD`(3"
        "vtF3noRR#(jk>$7Dt>t$PUAbv4b}xtdFJw>dpHj5kZzKqg~zC+zHUg{j4GJJ=8}dXL+P{CJd8Vg^krP$}*0aI{=&RY}mE0yd"
        "fs2j^zFXd|jHjnd~q!ry$()`<BO^!;0^uv!0TN%(`9k5^dv!J*~Lzsu|1T2A2F`RZ}a8vh@)!I5p1{l$Nmf^7$^ufRTTyQCn"
        "AF*xa_tiW_W0u4UJJumKZF_hilf`1E3MerXMXxIUWGU@4J8HPe<=UQt65;u#s4YjKk-7HXfnv2ZWiuj)Y%K6KAgV$%SF(&^d"
        "|P0<)hSW{n%{2EA|qLr$TVlZ!9*2g3Fg{@4WO>mB&_*cvkn0VROMeXRS4!H)p@1I<v7Tf>!#3%m#(UCbkJ9+>1v?^ASYXvoW"
        "6Th80+s+m-YdF!2Ja-MRr}V3hf3~e_pmdS@Kgo>3YINL<wt)#XouWpYDxrt^c<OL#^0g)FIrdfdb)()jkG)Z#k9<(#3aNP|S"
        "d}Jilyq!Khp?#w^#MU?r=8lQ%=IMPZiAs1CZ^~zDxAq0eR80~+EAKnD^)pabCDmEH<#4r>)6+}-Dte)V(O5O4FtU0S@zKS>8"
        "{AgZZHLrF9IjJRtF@4P##ycFwv^yiiFvUT_S2>ui5rh4pH|WvPL1KChMh-tlbgTjZBYVXuljc#0|0uyyRKpe1~r|x0aGtyIg"
        "pb6b;8=iaAH;^Q5>{k4Sl!DWfi!RZHZHlfZ6PYYTN@R@qz)?@q}0@}|aSitvukZM<q?_ysv-$So)yWw2y{D;5%g9b@E!T#gx"
        "r(&1dj@kD}VYkS6_PSVCg10rd*q?7~kjebeR4C~_|G29^!i>&vsQ}@NQ6WTgn*s%|<iJK<K1rg5k%yzJ_EzwSB5qAlN8ZcEF"
        "6Um%!)?4hdBvTdGQuV8~fX8N)FbLL_NKq4+^H<fx5-1EfM6-6vX{e}}ns?{NZ~NyznePWbZBS*M)UdW%$O`jgDmQribT8a{x"
        "u!2~H;P7f;$}0xqZ_4SeJB-@zFUAYJk*NDyT;dw%lNw05lDoZKO;g#^TIv*e=IyHubt;8HG`VuM?T)8vyjWMCdoC)7WKt$Qo"
        "cUCIfF&p07!|x#Ta&zqRmdD+(Va8XCCLksw23oaFnk*&tAYc>#8Q@Tuox2!Py8VFk8-3mC$JKQ7$66RG#ea?jrxkN(hiOzGK"
        "(p|Ctk&pa|-^Y~mG63#^Rfv$sYR>#vCap}DcfUn$a0vqGNgVjljR&;^X~p$R=h`SV?K4oq;3%ZkRkuF{d&Li#lcSmZ{y3oK*"
        "T1?M8li?{<{c6jR~s~{;*6~;{Cp|G+c&SscQ+JCvC2-oO3E{C$kLhR<Nh~4}-Vt1^OBZ6SiV?N22;VR;%Pmtw2d9fEh*(a8R"
        "iSrnra?9b|%86!y{IZ-}$CC1{1scFQK=<Rk&p0M7#UmA9aLm#1e9f!s;>Vr8?9Y}No*!R)-=oBUk41@ryX9gQ^I!FUK7E2kO"
        "Qx~SZ112Z(2-SM&EhU6$F#nS=de+5Eq>USVvW$|-aX!Jle(lT(6$*IfA{7R=#qAa{3C&(gw!N8AJtvbMdwKIiS`RrO-i_qr7"
        "mk_?kr2%cF7_vuSK25JP^rv<?`+VZxL6TY8{9qp>fR58*UEk6&atzlD#Q4C~&*RwzSB9O0@-$1LV&Mbv&^bILU&&@f2^<qFb"
        "8lOk@vwyqp38^Mbn;<vJ8=19QBU{8!*TFc~i6QFXCg7Myy?nWBE#Eg8r56e4znbGm3+#+)@Mkrvo|J`=qd$(+hgB#0eNyddA"
        "UbtSVBjSo@wjFhgVEA^UV9&urxDzizn>Nz5?JH|Un!miMCN>^Xap7^P_3g9><yyFyuq&PJj{MF$KB?NSRE4SqAO^P+>zUZ$g"
        "9}{-)#-$<Sq1{9ailU7`6Q!K`WJpy}BVP;FVlViq4rfcgVDaTuR(80SN-mIY^0m~@l4*FS@o~w3utwsx2-&Nca=AHQjD3?Q{"
        "fkQuwSxSl$Zj&e(O*fX!8brNCBY&L@j4GF7K_D9lmblDzCr`dygojM(ImuJvd7d}f^zXV3ynkLOzM$D<t0!~3b>T|Qfwr@Eq"
        "ZRqNA}_kPLC))nV|hlF<2}Ze0M1RAKobvhjfN`!8yZ|7tG1BrH&>M4%2GfaEfdcd?ShFb7+Wp16KScDM!xywHA_oiE%9ri0B"
        "m^;uZuw)1s=j&;+v#zT)}|Ovhhw#WFu^lPKREzOuJLuS<gVebCkdjTo={gGML5;6}F9jPxZD`k0*PuOy1??&qXF3HN&9Fhk}"
        "rjT7LnVwnRoq%SNFIjnobO*W4=uMaLZvnYH_%4X?ZRPME0NG=I4FpW#9mlXRn$=P}ON@^h+*B9RvYi|d2jiSc*cZ!>c&kY|o"
        "Q!2~G8Bm!9W{@tHSF>d7h1WK2C#DG8`#L^P&6=c)0(_M+2uvNAyb@l7!8y>#3NO_&noPjFFRJB5G8;FGYq-SAs|U<O7WQ3Iz"
        "FA(8nN%kpV2mq{<=;m|lMFadKBOF^aXduP*Gx<#6C)!J@;OV5txr_+nRtP?_BJW3>_TZ_U(IEf#W#6O)lz5x4}}i`3tSN2Yk"
        "8^)bEbYe$+Lv?Im<kk35F41k3CHsg#_(UaYLD01?PV_asP_vOo<YjudwZhwXqaT7$pO}h-aT-=PJ3PqNZv%$*UCxAn9juDOA"
        "sOwwM<omFgJxS|nnc=uf3iRi#25X=hb3I061exgCr*q>UIxyhC(~X|_f^=;HV;k0!I&=SYdv3c;loFZ(!KtW?agF-F6aV4h`"
        "q6=bAIf`u?wOVSQB_@hT9&n#xkYg>xVR8(}Y>AP;0gIYS7b+5DR8vY4}4UGb%k#*-_C8gbHfh8IEAeZS@NgTa9AeXo}lIIC}"
        "O|mFit7B2Ph_l6v5GznB!$zbw-`(=54^&iHcz7&@0<y5`g3(CNwj`_+c4E@PP++;sg@+;p)^IHLZpkCOqp;FjNphogQ2J<w`"
        "XWt|umreJ2XEDwWj{O9Y!y(3b<w`r^vYqaP-zP?g_YJq@UHzg5t*hzEK`{jepjLkuE-dVMx36cKhRv*|AYJh-L{<UL8k)xJ8"
        "p&NFB6@UlSDX@b{8YJvr<e0WKE3Ea&xf1vEGp50OW{gFp^hIeAP%XWi%P8khkyIB(x>Jj2^y64e*AZf`Y=*3hkXn4$2r&q#D"
        "D+uT;^|Q3X1J%-AQ-o}n50eE)g4_tbjMwpr0?Bd$oPJQn0^h3)fUlDARv?Nj4PF3#uE@vzih*D2NurCCwo^cxiGeYgXZNk*|"
        "i(&pkT7JhUYNb2cut%$$5qiKd#&0$LlCLyea*eP?+SLl+Dc`<N}=P+7=Y)<wT?QJYOhn-yj_uZi8Ak52xlGE5ky8`=uN_)XM"
        "MNN7h8T+(ihO}B~G8PO)YmLm$K^emZn3D#Z{v7CVvn<1e?9y?KFYjDbRyPl?3+-JfAR1sDy>dC&R7~OWpd#-?MWLq;u`)Kn!"
        "@tgA@trB3Agyw-5botRxvcE7CyaA+6o42NpbJ&UTOxe)B)TXStkds#yGKSR{}j{zbU3d3Iy)Vx&Df#~phA~1Dqsn_&wIPOLE"
        "GiD-6m?P^bapDbhwTg!Qwk8pGJBPi=~85>gNudaLsin9W_;5cIh@vigtM&?#Ql$Hx#pg*xn~+Cv2X6Zf$i;i5-`PmZ4jLN+y"
        "3znP)@=Vx>gI-v|-+tUYYQjtoo$j93NI8z99@ix?5QC3Ze7=hh^StSW)MJW{jLba^Nu;VOX?C`NWcm3j8iOtD<UEitrpKm~<"
        "Fdwd{l@N7I0N+zm`BoW@;26^8Q<the&eh#KS1MaZ{*ZH_Td4uLjhZL6@CF2)E`C=7T(wuE(K{nN4h}3sqcJ`kE-#sC)7R{L^"
        "Ck&_{YmPB{9Fw@X1-;oZ+<=|)XgSdg0^$ae_z<BJ1`(Su#|e|zDKAl_kN3tcKM=^Gpdg`gF9CMV+vrv`^WxTO=Zp;X{AIYeY"
        "j$2f0g>~<iktwHTi9r<#Tw2*Ynm0qI7OACS;8?GAD8{3|2HRv8E4|gF*FWM*A)o(^DZQ(s}R;GC37)W7Zyt#fug&M93he<=w"
        "6svbOocfF7su1GhNPp=o?VCz+!pYeStjjS@)$`WJy{&6L=cUlNk`e+qWn0B~3ZafLXLFl&R{jtiu8DS>*$7Lh1_Q=M3m}g-P"
        "yedlL_tMCj@ip#U2)!$6@Js~I7uXx0cz$pY*m8>trlC_YHObJMA3VR62<(@LfZC$i<)40XfRedoqSPU5ZM<KbJ6#hX(KRc8c"
        "8Ksq@L*ufFQ>U41i`BKaxueP12L6`jq%q|u|T&}QTcS5^T&Lya8V0>EQ*2w3;0VyQI+PXfZcM1qE=3Ic!9C;?xBzv9=_5<IO"
        "u|_{4pn|0I@bSLP)BWSYNpCuw-?z+GXQ(NO=<Uap(=|h_A#)5JKE|1vY@CWs3YR9yDHX3s5S@U$Z#o#lK=s&1TU9V@-4`ijs"
        "QHUKU(>y`Qqu+z*ws$sdB~uTcZH=99Kad~q;s<i($lKvjZO&;FdjNsc{cDfir;C`t(_g=ia6VANtIaEyE~>-a5!WdPS31Ug{"
        "*QF3b+LbMHxB<bF-XB0*;`8prp86(Ri#dsILbdO<htX)IT3G{amd;Q9;)&>;;#(j}WtK9McDQW->clmV3t#UgFZ1k_yHe5p>"
        "u*nPNaU$}v0O{psOJ|Kj5K_3_|n_@RG(dVKmFQPBH_h)2gK5Hx9{R0CZEVi9bvJq^fh5q*wzCj$bX`7-62rWv*|Id}{6bB*q"
        "fMXdq0K_#0Q^OEo&6}wX|Jj;1f(UYQrQp)K^7&t<BklCusa_r?UT23#)fZB68y2V|xh=<v2rGObW3gd#de&~ih_f!;tw;rh("
        "!<<WvI;wUc-lbeBfjB#g5<%V{6BQ2r_3os9d|E|S@PRuRlnYb(<CNkgNWUGINrEm!%3vl-e3DfmZ-6TS6ADbpraX^Uav&^Lm"
        "yI_PNZJ(b2n807ct315ih~Gn6y()sSS~?90pz`(V_PjD%tG-3x(sT?!_~M(jbr$5GLho$)EEOZ1y`<K;S4$<oJz~%eN2&@aO"
        "2Y@#l57I1lQjV>8g$HZdSC~#+%jAKnb!l|E795LCjDoezuw0xJnq`E|$mzF&-I=xKFF9_WMe=RrAG|#u|{e&#nZ(i|d?-Ppz"
        "R9u|Et8a!JLM$SEfUre3(Tw1u)9I29)l)k~B7MuT*jBHj@ea&_(P-ICgc&vFnU<&zz7c$=!@<t0EnhzL|+EA1`6^5HiZ@(<i"
        "8gC2vU)180*Y!C1J-tLoURd>l1;z~t|-J%FiQ7ZGi0rs|{iv5rN$e+x?0TEFfXUAW{65#Xyb)ZTUeZ?t1$k(XW4T<T%e1zv="
        "t-+^HwrT_^96oiIEBNH4VQ@UNDh23@$ywb9CY1QAi7$M3^Hc3U_~YHN3SGpMIOhnM03HMqn(|HZxNE*8Z+0$h9<_3&D}O*ic"
        "e3tqmT0aDQj0RinbQF|L`d)!9AWkcq-+)9j*5xLYi{?PiAPml)^W9nR;Y!02`#waU6KzI6hh4bWc89Dt5fP#wnF1>kbr^PSx"
        "s<BrgGq33d^>+h_Kw0FT=l=S;;vG$aNhI6lI$rEZMRkPqUsZ=DRU~hBu(9x}@By@OVX>3LamA?BgTEBcqB{&QHPA$1MFEuc("
        "T=R*9hio6g2(oHAQemV=z1b+yXnX}G@+*Xhag=i$>`d!6#2Kf~luP8MP#nRVw!t&jcA|A{*P+3ma>{@nSw`)Q~BNJ?w5q^i~"
        "ZTl?pK{9OF)e-mHsUU=F771|Uni^$n?;B}}EV5SQeM0pBAM_9}y)r+7+Wf!=hp5OuWQ^MOEXV)p0LnMTkOLW#T!6}|rAQR;A"
        "5JIbrX6R(TEvWik3RG}=;0_Ic?4KMTQ3Vk~nc)FC#VVlVSDoF1d|xdx{4u2oEP*UnV1mw)@k(_Ku5QLxfHjDve71=1zV&$ut"
        "NJZ$H59RryM!VeuB`Jbw&UKN(8BSDZO6SkA(h_uZ-<Xm_xku`U_Kn5UYIi~$%T(D&(2OHS*>+6c-`6E-}7>t_S%@@fAQ1l<r"
        "|);t#F<RPZ7LX<P)G9cZimyf{bk$hNq>wqSsC1eh37LqpkUVT9|h*Ud|#gnFFL+d;oTH9?!FUHKhD*`kbJAS8Xb)Us|9q>7*"
        "d2ZT;7nkEbC6&VEcao%|*fRGx^BeJT!mof-rE@)|IsEAdo8j2|hZlr(6sl!jAxIw0~DwFOaLxfUE#g>I>^#={S`FJjGD$&y@"
        "B%<TO0rebMF&yrw<E}Ued5Okmztx_}^nPT}0!16T=$K#=q&~c7FcCD+Ch8h_+dC(uRC5Z*Fgy?DdT<`A^XF#K+In#^;Vw6zU"
        "aKe=d;T2k@%&aF}tMOFxh^K@NDx3`ki1&{=9@+G+ivn(FA8C1sm55CWLkU`ut6Kc+_cnh<#K#|?X7bzbTc#Ny$kgge;mMBHg"
        "&*L*cHF;^-?sc4Br`%ngNynZZ#2xTo0RdqXtlk;KTDbA=XMwQ%%auqQc{+`CV0okTjcMbac4fSu@y#XV_stC*j+A=W}0Rt3!"
        ";2pix-5aNg`%Q<oPf;Q^X#2(51CU3JW2F_TBN}@uf|T)Ef#kUuOuGiM?0%K;uQ@L_=j`lIwsRsl!H&y@D3{lT!YqM@Q_Tb%-"
        "D5(ken8dtfL~f<R{4_t4jn?wMI6l~|$VC%MSJg&nkznrwF#nHIEHQz8U3lCP6w1!^iLrs&Wev{R^-NYHl{!$3K9om+R!DO)2"
        "H>v_d9KqkO#9Fke=SNv0vAMPe%N0%P%fZ~i}syPsU&Tvw;TZ_eYTk3e!Fo#ESl3FuY)!GK~ut(nRZonk_vz(${E{<5ltww&q"
        ">|qnzcrdaUzQ9xCq-q+rY6xa7>`06ML*AVYbtA?+=r(!@&<KYJrW2{D`!8RT(f4fcW$21a0(IAOv;vmqSutD>s)Xk*3}`2@;"
        "@!cIfWYW#NCcYl)7FN&cfdu$bpbk}3?%^+t`PRevgq|UV7cF+S+-c!qKZgfoJ!kr4^fzXL!>-h8{CWFZXVn{#Dh0S693@f%^"
        "_yH0?Gjy!mbVP;;YKhY2@x2v=?|o&ns#n$1}$R*d2?5JSxOW!d?m;{;c-0GFxCI5UVA)Fk?t}9AB+Dm0@*-GRi&c+xRj}X`^"
        "I=3I#Q+%zUGtaB?aBk``=Z)(eDj#_vK7nl{aYzVGmF{dr9CXj(Q+<css5U#?GtJ`Odq(l8TxphIKmRJbzi@iV@?PoMj@7lFF"
        "6>2!!3f2hT}I92b4@Dq5K?l}u@o*-&$Q4NBofzC#NU>yw6WC9oC3fz|<r1qW)v`{6Gg(O4ut%xAE!h1+l>F`wiebz}*Pncnu"
        "0jti^vT+^s&4U+00*+03><q*0=h&{l!kk8`GNrBnkzFe$lA$$4`7qvc(77+cDwk-&iQ4!ZyF8hpzrKw@VSj}gaP(BZfA9kNF"
        "zNwh9_0RDv1z$kb?DtS_OdA;`lsj2YNvvGOUzc@R*je<idKBjL?t7alLm&Y>Q?6W?<Gi<hfQpuErRf@Q6ZwyRNGPPWtX8qY9"
        "2q-&8dKuoVy(kY@j<-i_}<$5^OD-sUrQyFwi;So^Ghm@_?Nr?O?9IJ&@mh4-mrYfdM&W?;)0@;;onu8NSXB6CpMS7QXcal@+"
        "uDM#~|d@>JZwFJ3$j_jfk~v^0487B@M1`g*2?HU_CiKxzeH!ut9WdH68g6|{d}Gdo13ihsqM4vPWZyX1B5{G~Nw)C=ZJcAn1"
        "J6(~w=qRXZlyCz!agLfzW!-4oj3oRbq<^jnMOvqt`X&AdC7T*p?(lNcvtNYxg6fi8b<@QBJyMCc1J_|6sh7iZvn2Y;%NedgP"
        "cgMa(SZ7HM%Q(v*;-R>z0PD@ASq_)oIo}d%JD3xKuVF{W#by8S`@xah79LAl9Kqo8WidufEpo}2yJ)7`8eyk*%{j-bUUc_0f"
        "gy)^#CO{L%P0cE81>_L;-cTUjJJcsH~rJ&!~Tivr=Es`jFrT09*b~M1(VG}sPScUs3h!!>-h-w8UPLTLmp1x9I)0v)25<o^j"
        "Z;$Y!*fyqXVk@SJSE3;98W*wWH1Vxu32=<CzR>hnKmt!~4iut|--<YENOq*eFZV#j>o{cHC7fptbJV#W@w-+@kRF2kH!r&@R"
        "DxW5J)5O67KlY%xobq{s`T7B7+~B7o$QDUNx)3k3U+2tGE_B3`LQ)R;jER{1SqHn7i(n;VF~6ASM(G@9xPGjFEa*++U|RJ;I"
        "m*3v-4y0yGDaZz0;(q4c~VdE>oaf@l9HD4Oky^6~_tQSN|x0TSiY)_v+Wt?$nxf~py^=rrC;(ml~rW7y&vAtn;vYao9mXtgb"
        "Hx3D`4x8l^2Uz?Ys@%=;;-D3T$f0{SwRO`UaUL8XxqZ>>wNnCylgnfrE}VRuV3zA|zvJsu&?Di$kAmP4{OjYVpuIlW&VdPj{"
        "&jaZFgxTelVhNeXccHp+CFxRn`r;(vz7)=ciiuJ$aWVF3bYpw7cN+q)6NS{ZKry_pxy4?#J}=2YIz-n>eb`T=-Q##c!4);cl"
        "}yhQy)v2tB$tBW{k;PJZKFMd-eEeaC%7$7G3M)6gkbj=0s;m!J`^F*GM{2V4YpBk|2TcQk74kbbU73nLu#C1Vy)hdhua!u3d"
        "AH|7y(z#ql)@4Jcj$q}ElfQuGQjDX0!iZa1oc^Q4e+avx#RRre<rSc-tI{384j*MdsaQJ5n|fCbl~(%B`x7tKN7OysK7TRI{"
        "ZgXSnGAOoY2HX=E&zYkc*a)H`;6HbJ9<tkti7}xJ0z1xlDP5{)0lWJk^fn>0dzo2p0TCg@cI|-Ak3dF#bGBjfc$iQf=QZys?"
        "o1h+O5_Y8od72lJL}<G^2&fs?2{Rxx9EA#DTP4g@v$D+&c%DY&S|*9G_;4oIOOoh#WF1FVSQw1>!p>cp6s|70s+)5kC1%MU8"
        "|Q%>f7Z?PU|}0D^Kq*#F3;Y*14Rqbaxqy(L>8+PwXV#^r9B+j6^EJUP^C!udQ_Nt$7PMca60~#;&s?kAB&BJb_zAFBxrIWX6"
        "$OZrXQQ@*tQ>+`!ThNtp287#hkqU1%UHP%MgolE^a9l{F0xLRKU$^GVl)5f)6(6OUh|gOH%oOEUg(3Q~^qpN&UBB6~-g9C`*"
        "+t6W&P85T{M(hdk23Kg`+r(cs*C`;+1!RscoieQkk01#LuK*tm7nql8+O6rRkKJeq2!oOTV)1g)+lU3%Ftd~p@9<bb<rRF?0"
        "z@<^uDAJm4ge~pPkcxnxxDk8Y)b;-nk$9?nE3G#XQzgmZGxz4PHMCF(*9-{4L$&yiHdSBIkqj{3abR%`bY(kzp(^&9H^q38M"
        ")Vx1lQzh0*wn4Md;2Za?)eKOvW-stHTq9CY6?B7_h!kuZi#p~}r^iTg`T{%7;rsJ*P%F$)|FR!Y)|K=_;M8SjJyPui4aZzIb"
        "m<qwwLJ0S=c|&pw#C@oWLJt!>7`VI!AXEDDDF9w<kg#_?&ceh24P>2FH%N5r|@v|;|#;ux>{*mJ`(M(7)jo%!kSrzL_EIbqo"
        "ENP9AXG<_h>xKxj@9!5B&=R7RuoC2zdY5DK`@Qa5^}DbU_t`$EO#U=kK|JpeOfxCK&vRiGpHA_fYtB$WRr?ayD`1R1IcP!D^"
        "^dTs7yi7-^tN?mHe}2TkzrP$p@pL0dC<bsD5pR?<ef?{yD7xcMZY&>dwYjyOH-m9{lOoh%lR7TXD~YII7{8Lu;A(sTeE9*JT"
        "B3Gc5lf2;TS?TC{iByf^KVP(|2!+A2?fO!RXkPDF$ZpY(|+0<sZqm9WaNmX4ooI$DqZ}kDC1eYSiNhZsbdRz~4!e;CkZg5&q"
        "Qd{9_4&#Dn&e=cQpbCFsN8_g`P;b7`fBlldg-VCGSoh&9yDs8?4=Kl^;{wJRLtDsz<o~$NI9<|DnVw{>K-<1N27;=+j6Pa_)"
        "dFv8hTa0yLy2-2z7Q5>U(I(^T0LBIZS;&$Of@t}<YtkOJ`-9s=9%Zw;>PW82HMzah;Y;%fQ%Nb!$HC0^GDdgWSO&>A&DrjTn"
        "~Avs&I|I&_w_TjbGarVSPH?t)XCScC;#)n@Q4Vm`7tB-0XZx)futC+BSU;K1O9-p^Yd++@O@VsGp)*aD0kzg4MQs3?D__Wbz"
        "hjmAU?#3rn;k2MxyJfSXbqDghq-rY3HIJ!11^{QHP&wOOz8m3PE`=X4BiU<L!y4b}Ka%l1+4kV~2vB-Ra?rK0?DD_@N5<1Wc"
        "zA%gjcnXmKzGipAk1+=w$nIc#ca198hC5jO8WXfW<c7`gOhTM&{xz%vJO>je0&-VT9-OEnycbCwB$T)~{ne#}?cZ3O8V?Hvu"
        "#tz5+<Xo5YUL!}U@*obRuX7+-w;k30j)rEw#9V43>(}B^8+fs-Xe~}_*^Ol{Z0U^Au;w%q$6fr<Jno`{Zfg?t*N^5grs`<Ks"
        "vbOAo$vVp{VJ#P*c`LBSIWY;KJo!H<HZm{f&J%F9>tdm>O9w<PC>1G8Swao9${ulD^_}_^2<u<z`dMP9LA1qK43Y%m((#-3-"
        "{r(Q-2*EUuA|W+_lO}9S_xR->7$CDj0=Lv`PRO#Wj~?%1=eDZB>*?P$)5#%;iivz61)$j5;gCg^e;uMS*nEQZQ<A9#C5=?h1"
        "rJ0vY#=;{hv_M$jX$McCL3Pdg`@GvTr$>UKs?sIyuHG&%2Ju#sF}azQfsnJ~fOn?WCB$9ET_Z$|pj>DlGrVni9eZt{xjQ`kZ"
        "~>1?WQ7#0H^5dp0BZesUs;2Q|cVx^`W))Cm&@NPYbm5oQyubfX1BVG)3pxRK4vwweldUWC794kDir~d>d3Bt)XhHv03UwG8N"
        "TbmwjVyc^-UE?3{pr#bVv&>R9UG96Ht;w>Uby^p6v4>gCy)C>SG|87Q|E|t4zWj@|yM6CZes^wl`w#+Kc!iJZl{uhHx2hk!c"
        "F$Lmo+3F<+?FAeoKC;Dx$gvbiL3U4qpeu!lPKzwT!l47$t6Ztb*oF(tv248P|=VhUsci?!!>=Wt<{8D6J~vJTC(GEPUYfh;h"
        "k(x=bn4V91e-tA=O7KuHokf1Gd0W`$G}1li1zPvC6f`WT@K8nK)l-Hme0+dhF{b-q7dNbyt-SY8--c3tVSw@vVfl>)CFgI^u"
        "~BB)c06(S*$ssa}k<6h=H#AtPuNlx@di6b_7ewGFVYvGEZeXBE+u#4csVqL);okyw|+RH@1Z;c%fVCYN?G99bY2E}JAm1q|t"
        "f*|?ni=R0!skYkPQsX=31Gz)mz)!<4s3_FQ*U#Rh9S;n?$H4f|rl3Zyz?o;YzVNi*&ig!xR!;-n_EX!=aV~&=nB<8X;q5Hec"
        "a6Er4Zc1P|2Vdkd?Fwn)L+d1{enMUB0iXSWX^zoyvW8hZXuR|E7x$<ek*P#xJCx5`I3F*CSzg<!K8&AgKjL*Q4QQkK_;m~lX"
        "ENrW(F?vD<3%9q$|d|Qz+VEx!~ei#lL^BI^0$ytI0GtMjGLH#t<b#^F!i&XtDWAdLpte5O*rm4xbOPBtGSj)w{o%oD2Sp_La"
        "hjZf#RU2b%kP!v%{-qb&f*msG|*r>2~_<hLW-_LL|1;YO=}O;*Zsaa+ttWkk^jQ15RtoGiue&X%07;?ShN4gi(s*h-La-y#U"
        "=^D-+pqn@F2lf>F4~yvHrvD5ymGa^i-L;1GDOVggJ_%C^8yk|$iQp3Aj~CYrrL7FHyPE6CoKC5=F;Q7)~`r?Vw;%LXyCCJ(5"
        "Frha_uH=Xd(Ip~K~K6F%eP_IS#gwVz-i3@8{h)FdD;osx03O1}aESFEJ^WnTd@-Awco=_L{&f}F~D>}S{Ty^2!zO7372Vca-"
        "%7e<2UIGKL!^)S^b;=uunxDIYI5+V*wZhonefcbWy4TPPV~~ifs=67Btv#V6PZS-f*>LF`L9<*|QSq&fO06s<hA|}|2`;`1&"
        "=*SOg9)_&qB<IG+fr~NzUp9{a(s?4!8sqDt0<{dy%a2a{eA%S^#T2-==#wjzawAUFAVRW8YWxYeUxxUupQ~!{!diabpGCc`R"
        "&=!Po{r?xqcSs-XBe@;2-vDkoOjXq+Nset|K7aRO{*;`h@fg?bJY36m7!dK)94Y30An#7<~cxHt~hELQ*XB537^mZa<O+m&K"
        "K}l3>Tu#-ykhS#`CHj?1v5z=^dNjAhkZ6KhKq>%t{&MOhT?{WXP$0G0(u0u`4m^Gfx%D@ROqyB)6EJ?+08V3W?lzXosLU4l+"
        "|@)LKqvn9VrX9MX0N{?Rp!`AA1z0zKM#f2C-M1>=-LJ3J;ntfHakX3y|hC%&yG{ixy5PVo+uRolv@eK*qd5E3Dlaha0+>(sQ"
        "941mzHF9Ng3O*B7>X2(xVax82Ht{&bB$`*+W^HrtYch3MAJCo#v_AD)^QUY~soz+O<?5s-KBlDL#BV0TuK9LZ)+?41_Bh+1s"
        "Xx-%C8!lP*J_#zP6$fMdeh`evx3Ij@SbC}gvW35qlh00OG~S?#!v;W|FSNYtikA-9CTcnPpXkKKD6w*f~kQiK5DRXN#+InmR"
        "z+p!MB)i&w$x=>~o^0)p(OPZOp^4ixbP*?juG~C=$xaGn64vJx%iEp^M!0+;U7v+IIL&D7YPTtJX<vn;d5p5l|59E9_T{s3c"
        "McYY+RAX=uJWs%?K+t1EAB;xC#&t*u5151@woTBzH%S8XQN*fSFM19d+RF%d_lrYNXz@$C+1k8Sc0aA49d(<F_xd*P&hTky_"
        "v>h9IbYoOg0gcVfuXPE|?fUCu}KIs&j#jevhqK$AbmC3}xVmd6)X60>Y6BiEdDV1JV>6(nE`gmL*df&@MN*!P~RG=mV*O6-P"
        "O-^_LU^FdHDO8ohW%1tkM@y&B+yPzLlOA97TSW!Y^|rq_<r?Z)y9x*N6<cg~ZR4h4mJUC)p1x#%MAbs;vmR28MJphvdB2KVM"
        "jSE>)Ng@>l-2zY?jkbr;03?ewnNlFdS^2(0V)~rSp`|=kaY{`+z=~P2uM%SIw&Sl!wVzW_Oi54RBLPEQHHKOe8XyD)N}*V`C"
        "BkETkhjoCO^hGAtaE^;yOqNHlL1F|7VY%hx?B~_ut>$3!gu!=>D~lIF}u_%jM)zjkd(ef!n+y0HHhbm61J*c{0Jq3TxCzv6|"
        ";VnN?fis<_lcalJU7S%iWQ7Q;z_g#_RjAd#y(DlK`?8Hg1O=H1}jOV2(Z{P2EoLA4C*INj6y?kf-;la6)1X%dvcL)D{Lo&vv"
        "5J*)iU1LujbiP#R)n)_*T^b9SS!ipnGH<fSLN6_(W!kzOao>V%`P;xP~fMqQJf3I~+nA<{nvSx_d#M3gXq?>NrT%e1~<C7EE"
        "wo?plaq4WL$~ECbCX=35XGbn+Q3b<#k0%sO9b0MT!_~TqAa+eiZm9Yvx&N|7q0ZU${q5kp<5P3|_U+*47~4peu)4zX+f4kD)"
        "bNs)o)msEyjv(ut#n!Pg14>413H({$4j%Je{o8BSN#BVVh6r&fD={4#P&au7RK^L10)M|jca+`&+`PwSuT@F7ysu;i>f0&_V"
        ")I@>`Q*gjmd7xJL1B&ceneBv?P?^=-ou;5!Oz$+HERV?QLpLz7F{s@VUV8T%LL9x2<Fn$}teHknCPb?&VJJl6D)ihpyew$vi"
        "MW_D|q;n$|x;{Xf@B8UEF7LZNNtm`|)kz^rPmN~is?hs6S)LQ}12`Pkd%j}ZjC0pZpgNahXafWL6yYp&X(-V)twV^|~HdOyz"
        "QHi&%2>qRhbwT&6rRVS8^DvsshcC0^XgG9?>O-z3kWi~X0zkCA*wQ^oe(Z8?>`qh;DKKXrouS7j@BPz8ywT%smzw2OR$kX98"
        "U%Y^?HVx$(;g)M*NtQko&z#4Rw#dkq8|Sswe|}@L`Ac!Yp#NZFg44Eg+F3G<DMPWNd7hOz1kLf(9^qdY&_U%3zoTM9+%0Ydu"
        "D)%26{uO|rm^JLTHAn5VGb5u#kQ3t9EgW*D0MCy&my&5>bb{Ghjc9A&=#-Og9@N3h)u%*eJtmSoQ-I@jNI1ruw~mqM7~1I+9"
        "`cZCuZSp<iq<$tZ;oCNM2MK2l@4me6wjSC>m{B+|OFyR4JMA?PA|`zCIY-oYEFf)oZ43_qk50wV_LHwOG(qFnm>g$mU+J_aH"
        "z2ajA13o^(|rh1C)i{~X)*jq)X-rGjhY2wx|_?y(B*6K$J+^;IJ7zJY2bJe3V>-`nK(@a*l|<4sMfH`$%FG0x9UPQL9QejhY"
        "RL0rW{?YxR{Mk+b1A^Hqw@Ru5A6`N|Ku`~^=LBiI7Hx&zh>x@lp@YebbCh>dwAy%0Dgflf1Rkp4KFdu5He61K1)k*?J*+uYE"
        "EK9A7h6(|TdTzgxMsqGvV9|>>AGT?N_?c`zG8rEgf0)1zAY;`NA@k9TR9DO-n=Hfqs9=_r7>$@tU2_!Ak}E=dnXTAMRxxMdL"
        "^}F#d2o(37$gYmUUE%k#EHJD?qGqfa#z}blwnN~)*(ZOxW|91E(77Wd`?7?)W(e%Ndt8vtu=T;9zvKq8^QQD*B;i(4o!<rXf"
        "qR?2EW17e{ZYCa3}3pxycVzF2Azb*OX$AO49e{F#`se;6@CJ+K;D?h`+c`4L3j>5tY5BIegU?Qw|hW%k@MADmU0>;M?`C2om"
        "T-a0klUgl#1^NSj)xWs3;5xW}DY$VAoQfOu$6INuucfKqX}tHTu?K!i9!nlpmR;J?tgMZ^1?FcnahV#g4++<A_Up_fm>{b$x"
        "OG?WAw*Egco!~|Jbz$chGqQXSiK3pt|n--1q5q7IYSn~>dlCRKb9DD-3Xd3*Sf`m6r8gR>~S(o$##QG(=SafO~j-E3rdDR4l"
        "fm;1{@6OLaN)IoO-ww{+Uw%okYx`}Tk(R5~?qqcM(hb{xS!By8++Jx2e5J(#p5wvZe6P1t&v*3G3q$SqH?uf5&djk+7C+}wE"
        "fmib>5B3x?P#-(-60AX3+znkxom9M6fu+aGNaNMnAXVO)c>NPN7~9PNzJ<z&|7LAw{7Pz4b0fLmb#nNuf~Fd<N|(65o*PcQP"
        "U~)7ps~7!WO*)_fNxi62ygCkO;d;cNDy!dH4Y_Drm%t_YAvxizbgfx;8s*s{itT;T$Ym_h>VXKc$yhKZJCduI#)nyH^b{Z9Z"
        "w+j>d|;hGX^z``Qy<JL-Cr?CVdx;key?*wyLf#iQM@M^z0KA1Y>G<h0&_x;VTT9G;yXU9@XYt(~i=MSMo`(q6M_)j$HoTA%N"
        "7y3ON#V6jgck-)w{A(foKjqj~`1UDB>tER{485Yi!!Qt*c2AntkN#jbbKy(i3dMXMKb?YN+lAzt7oNt>CmGgvChUHyhR;+Zt"
        "Wlt>@zaT7JXSr}~h?<6ziK=!Hff6v!q<dj1%2>jU6}$9qZN%3!7>A0z)LNfaaUueNG$KQg9)#JQ)aI>^MsOX{*V?usk$M_xy"
        "47GxU%|z@-7?K5vVp`l{>GgcwhFN))G)+0#}hh~i^lkOJ+2*!QkQ$oAz(frJf8UiFCvpNknodzq~)hC!>5lMX_?5eOCjS{?R"
        "q_c%$dZQ4PttZbityeY2+0OaD5#u9Bha<t?0m9I>h^TNBzq|SI4>}=Lup(NZP!*_mbSd3so@st0j9)FuH|x6*`!7vPC5tF?R"
        ")*C!iK=*o;ohv!ic8xl1M<pbvif=KT?Utb<j*<-&6MnGEYvx7AmfOw@+ynm1XB!avf{tj~<J<XJ?i1~Y_#^o8C6CNHQ)NvQ*"
        "No3tNFMp2#8o<sLxXX6K}8jc9%kFE}LH)I&a>!~SCnl-eI^#Hi$PQ`b~Zc?^L?i5X|U_5V*B$kA5bJwlK3o*S5lls6gJsG^d"
        "^zdMO7q!=UTb-`FLFmtoY^Pa7bVA%`LdS!XHS7i!U!>(+UE_fptmDks;Nxh>L@>l-m@MN_8}@Ng2nG#Wv{il7p~(4RuV=d*0"
        "pVeHFWQ{qOYc;>&ieK#Ld=R*>epBLPFqXq?3LymAy_!!18Fk{4<@BOa*e+%aahhHUSCS~(<#NDeUKz+-ArUH{T*x(g$|c+W;"
        "uBn=ob_lkgx$lLf~|$yf@D<4Tzg(+RoSU4d&PDU|LFNyGzow&;%`8(yx0~W)}X(-jpT<@~eV!%e;cB6EI`*yrGDLApkhSG9H"
        "Brta$K`hHzWei^*Iufk!D_s|KY5qQ2#+SY$%C+to2a5Wy_FKoCU#D2R4@>#xlzO6jdcBERgfl?e|)O=yJp!3j3@qHJ=iDx43"
        "<(pG!@HzIA<be@_7ZG4x4|JW)&k&(VLx82)3Pc5oirt(8O5|2<#xj<l{=CP{23a6Oe>#q3n_Em}F3JVwo21t(wtalTjMA7QI"
        "4HJAwLW%XLp>oI)MZ7c*nyK~V*!6$qVT%&md%zaUqkrWF|EcYL7*?^Xx_ZbNH8}!xlm6@xsl8CEwfHM|!p>LngPlLX3wHh>A"
        "K3Yec)-qIbN_e#a^l?ii|_r;AGq^7Uwz+q{))T4^FO_nUwg-Q{@VM!^XKk%)!C|^hWmqgU#;Bi{N<|6muywCQ9EliqekHUM5"
        "Ek%+njUo!D~%N?Mt<ju&R`P#ENSeEF5wq8hK?Jq-;-<G%0Q#GMSw}F`093BI@&lotzBu#C>a%$)l&plZyFmlRRD5a@E|o{In"
        "k+;+z{yRWk2wQ64JojQ0%lk+PXP>DdW-HwHP>)HZx^#LdGVQET=#f9nFEWLc2;C3P<~KYkkjYJKV)v*m<g4>Q!X9GD#0Vr|W"
        "Lb!HHO^AT*QvqGHx<HdU6!uqzAYsJW@aNVs3$NHKCx%M%&L?CENeyC0ZX!r1owP8F+!VRXTzM=VY2i}WcIUF#t<1BcqQcKFn"
        "LD8ltWWZ!c9uglSQ8&4^sk+pA*`d7!f!AAtYB%zEs}4cU)z;`=+uz-L8Sd?xo&9IecEdf_i>9(=aJOSNjTtDo-so7fN*`iqR"
        "!ZSE0PC*%0V=*&hW%LK8HbgUJv7|eYmas_N@UyW-pAaf_PaGNN2Q*|T#&nkssG!->oef!rA-@F2s3G%-l?>t?yD5>hnppZMA"
        "=-w5zd@0miZLxcb%J#+KJw<4-H$_eXayJ`U{Q0Qfp@-p)y*KOHACV<j{Ju`_iTVZNGf>l-rQUmHk3IBG*!ZJ9tOVpXB+x1;A"
        "Nd4&0l*vP5P7Yi%QGY-B^5uZf>|P(78_*iUU)1N*J;5D)NobDmZ;3#+E#*KX?{7%<!bA>0Hb9Bege4s}@JH6-B*YOrzbDnEX"
        "5?J0AIAY3U`Cw82-<?27)4fpr(>c7~nS7mRTL%~m%PSl=gO$7Xt>EHU}7`jfe^o*aBLNu=l?+8@k9Hk2NQ|*yJU=8fcE3&OB"
        "oEdw-JWSY39N3IN%7r4ByMrESMAE}}6a_`xR(uRNy8u;mKha>~*{se>*dd}^Y4`%s80L64*uhzN&=knLu#i~Tr$3nVKqTH)c"
        "wwc9>y%h_?NeNJQqLvu$D@4HU#RrbigyVrNHBp;W+Y@|-L$s(jX#*iqPoEOFxj@SYeV<6svhi5_K@=V$hq{<Un)H}NeU_oEm"
        "WRy%PQs%#AFI?Qf@UU0jl?hV%gvpp<O|=sXd|KP}|ygHmL*7&@xkhIOK7}@GOt3faC~7Jk<?$DiPWWrvdU|HdTP&BNCcNzqW"
        "QUHMVRK{6S0L8SI^He}$7~$M6{S)Bl<=I)04WfBTnEDLQMRF^|cAC+N-V1xf_77t>ZYK(_c}GyzxNZ2|`Fa$hEky|f<dXYS!"
        "6H&IRhIySZFLXq>^%RS;$jUs+k>2j*tw`+3jegx-laW_8s@I%Bxr0b}5iX@yW`A{;o+U<I>BSQy~hE7||5u8ReLxp<^{YBUJ"
        "MbN9@e><F+0k%8}Z|curJ6mDZ8o!xAZMx=6P-E%|k93T%H)u?M69j^f$odb5pON#G5{2>QIYI{&{vJ6%uCLrFZ`Wy5+Ik+Je"
        "?uQ`_<=$f)qkU(hpy*L{ilR*RR3LS8=+MaW6sRTafVT72H2~;T6J>jI#^M*f<SFmORm>7Fy3+d1)Gb4ElH{w$PkL8M-@Z?$q"
        "fJ#p?D=#@rZsdco*jE^=n`i{Ln5Iu_L;HgFD09ScOfnfoF_r1`I``{WWfu*Rk?t8OlZ?b>bCuU4p?j`?f9DUAeafb3!gk_Ua"
        "WGs=S7({u%gOJs{&46J0+eQV2FP&o(8lVe7VWMaQ<s^_aF@U?5mgH(Fw&65mGYu9jtqh!k9QSUFBA388zQgQ}KDG2<gwF)uQ"
        "adsfxLtFP)%2OReljbTmVVeuj#2*a!<Ww&W<k9WCD-#Rvk#q>;&Or4HZ#e$n9^J?t~yI#1z;z}^WuE?YzrEDRI4EPWNSin>Q"
        "!JQC8qRO>2Z0hfBBKX;gJIYDk1hQ7WXjQNTPP-EoCe;35iG}TQNyNPKqK!Gfi$9q3v*srSPeS#j&<1gRABp<2_~fhE-VrtmH"
        "vft9%xNq2Sh)quB7(*yWVi*bDplzswEqhseYdq0_^!6SN#kn}c@DdO9#IS88t6qX@#^>Qn9)pghec_->ELAq2C&DxBcK90zD"
        "8^E!qPJARV`Zp7tNJFgrhOX#E$AC4VzEQl6(TaDjjGYIO=uO3Q0JdF28nn-W|%VV--~pqPk%0EE28ZlKv9kAmMdzF&&;IY5%"
        "@xv*lcq?jl>Xf{N`Ia*<{gmcZ3zZSYJtmu3#(0E!_o>;usaWvF&l(Q7Pec^ClM+Ix1pyEW(qzEuaL<+?}L9q`^Tf0ti1y^M$"
        "3IWT+cBk*^BhwmDGxvqZm^S+(<;bvvwr?`m`r}uM9BCiD?Ynq(KP8m?PRI}@k*Y|xSJg}<|MEN!YsX{lk?D<_XBukcf#8$nw"
        "RQomhb%)+t5zyKam!!KZS+N2C^hLObxpB`QzX<o8@6PpPb*?~mfVYHe46&-7@EA3s#d-9=z*iRN?Pdw;lyet$#N~HRqZeF{Z"
        "dhKJM3iNMfI!v0)@)N-t7S_9&x#g29PE&Kw8n~e0rCUQLBe$Lplqx%fR0Y;H*2u~X;K&$;G!JK7TY|(&<@6FRg5T1fKk$tEf"
        "v#yfE^)_NW6p_uZfk*y&*{~c~%y6^3A{;4Gxblj?YdzXv2Z+1LoZEQNPw2MvIa2NwvJyRyE12$j&Fv<~_dBj@MGmIikJ%v5x"
        "KA8ClmMa%*f@E1rZ%bD>_XXL8&43;cW~SPj*VWOu5}tmv5P*;t8o*NDfry=tX{AWzl=24=Jtr8*EE6}HA!+p`@FPJgoEE}pO"
        "_g~CfBnc3Sk_0Wt%Ix!}_qB4CJ%N9=={i+HRMvBl8mIEQ$pKThh=<+;>ONSS;4R}>NF8wAb3<kw8a-d6O9=7Elcc%lP+q?X*"
        "e21pCXZL$VzdqXer927CjvkOM;U(aIxfR+PsHVq!&(d-17?allmfQ9abgMHRIA8ad?5b<N2fc-e!XFLD?g~__IS7ZCJX`ZQV"
        "Ig8o!8lovjf?>R&Q-O&t)>EP=?}$L9kt74P&dM&nPA;CRi>p1AHxpMS$6G-i+a+Y$cX3rR0{C?*~{?Rv$gc;2b^H_#9Ru5Pj"
        "Ot)6xbXFKg3;&TVc`a)r!i7Nx*#UJ$v#gG>#J5>(#84OuxUIT?aHwymBbKuP)shkcB^}ld7UWGshKHZmo|;g_R}egZ>erGgj"
        "c`ZM##&`=;wX<Xm^znxS}fN8BV^!fHvWwJl=!e*mo<Rf{)3LYZ-;)s(AK__5k*?^c3NL)t1WbhG9zQ`#u;ZsOZ)n{XSGBo)6"
        "8Ss*}esg2NZs0yq8SVZUnQ=blDkzI3vHnTI7U+A1D47DsVYUK;6(25)%5>!G}v<|iiJmSKc1u9YUC=CQ)0c0I9W@%f=jhL-D"
        "zzNFskXQwfE&-~XP^wg_DnLgw11PoFHY%+KB^7Qz^}3Zh!B62tPsoi(oRd(Zq9Z9TrM36;l$>yqMyZTFTLn2*LC}Cd{!p>-|"
        "Fr<Przn3TU~*HDQB71h_MtUk>w59sjZ=h!CWvxm(or?KNnBp7e`&~aONxePdkC_zrP0$$RtI|HIC+7Lkrkty1J!jj%qHuzik"
        "QQxRi%#7Mevyxordv}nAGDyC!TXk1qN#K7}4wtmrJ8<KWdp2=%E#NUtx1sdM=BFyF~NTq+&@jnVlQssB$QpD+SZfSkli?7uS"
        "Abu_RD&VN*#Z3rBI-m*q_t3_S&2CFn=5W269Yd8*s#nb`eeYfLhy^0T9%*XSW6U0}_Vp=kh(brhrnvj+kRh2dML%3u~zl1ob"
        "m8)L-QVqQ7~>{($W71Ylf;T~tRc;Z(p%7zt5se42;sJcZcM?ngQ>m1AnXus(o%z)%Y339v4&*2)#1QBVd5V-78n>n)$4LXv{"
        "nHusn&Gwa9t1Yqp<fIJ*hJ=}FZG%pQRu<}a4peNQfyEx{!gr($8+#W~WSFX@s|hz#icC1et|Hp4g?B@*#~PwytpY_72dPgeS"
        "Dd<X4G*D~tgtc}-&Xnp>ODmff!2y|RIf=a!w|r7iyBR9-f=G&j2+*si@{3nL(FxXs4#}@yuQI8YE%NN1GQ|eDV>b2O;_){LP"
        "rK|l|~#Szmeau$>U>ZPm;;Kg6*NA?9W%F?EFv2v06T-ugC7VX2n!FzOKiLd2?NL1y-{wwXW66taMV-1R$vbjJ~ckwNeD(H5K"
        "Qo{|C;i1kT$cFMbczIhfDWU6O3bGZ_BAS2aNYFK5OhZv"
    ),
}

#: A live-lineage gate is ~175-185 KB. The published-base pre-image this
#: repair also serves (backend/test_repair_live_backend_gaps.py) is ~149-157
#: KB, so this threshold only chooses which refusal path an UNRECOGNISED
#: hash takes; it never accepts anything.
LIVE_LINEAGE_MIN_BYTES = 170_000


@dataclass(frozen=True)
class Piece:
    """One exact old -> new replacement inside a repair.

    `anchor` must appear EXACTLY once in the live file or the repair refuses.
    `replace_with` is what stands in its place: for an insertion it is the
    anchor followed by the new lines, so the anchor itself survives; for a
    rewrite it is the new text."""

    anchor: str
    replace_with: str


@dataclass(frozen=True)
class Repair:
    """One anchored edit (one insertion, plus any `extra_edits`/`pieces`) in one
    live base file."""

    name: str
    filename: str
    #: Every one of these strings must be in the file for the repair to count
    #: as already present.
    probes: tuple
    #: The exact text this repair replaces. It must appear exactly once, or
    #: the tool refuses.
    anchor: str = ""
    #: What the anchor becomes. For an insertion this is the anchor plus the
    #: new lines; for a changed line it is the new line.
    replace_with: str = ""
    why: str = ""
    #: Further exact (old, new) text pairs applied in the SAME write as the
    #: anchor above - one backup, one compile, one swap. The card timer needs
    #: this: its patch has two functional hunks (the block, and the SELECT line
    #: that gives the block a column to read) and either one alone is a no-op.
    #: Each pair's old text must appear exactly once; its new text is the
    #: positive proof that pair is already in.
    extra_edits: tuple = ()
    #: A repair that changes SEVERAL disjoint places in one file may carry them
    #: as ordered pieces instead of one anchor - still ONE write, ONE
    #: `.before-repair-*` backup and ONE compile-or-rollback, so it can never
    #: land half done. `anchor`/`replace_with` above are then unused. Each
    #: piece's old text must appear exactly once.
    pieces: tuple = ()

    #: Live-lineage gates this repair accepts by sha256, each with the exact
    #: stored patch to `LIVE_GATE_TARGET_SHA256` (see LIVE_LEGACY_GATES). When
    #: this is set, an exact target is "already", a listed pre-image is
    #: "missing", and an unrecognised live-sized gate is REFUSED - never
    #: guessed. The anchor/pieces path above still serves the published-base
    #: pre-image; the two paths never mix.
    lineages: tuple = ()

    def parts(self) -> tuple:
        """The (Piece, ...) this repair's single anchor applies, in order."""
        if self.pieces:
            return self.pieces
        if not self.anchor:
            return ()
        return (Piece(self.anchor, self.replace_with),)


GATE_ROWS = Repair(
    name="gate",
    filename="jarvis_gate.py",
    probes=('"app_build_android": ("no"', '"app_install_android": ("no"'),
    anchor="_RISK: dict[str, tuple[str, str, str]] = {\n",
    replace_with=(
        "_RISK: dict[str, tuple[str, str, str]] = {\n"
        "    # tools/repair_live_backend_gaps.py (2026-10-30): the Android app\n"
        "    # builder's two cards. The published base has these rows; this install\n"
        "    # predates them, so the gate treated both actions as unclassified and\n"
        "    # refused to let their cards be approved. Copied from\n"
        "    # jarvis-backend/jarvis_gate.py byte for byte.\n"
        '    "app_build_android": ("no", "outbound", "runs Gradle on this PC in one task\'s own copy, and a first build downloads the Gradle distribution and the Android Gradle plugin from services.gradle.org, dl.google.com and repo.maven.apache.org - nothing of yours is sent, but build scripts are other people\'s code running with your own Windows permissions, and what they do cannot be taken back from here"),\n'
        '    "app_install_android": ("no", "local", "installs the .apk this build made onto your phone over its cable, replacing the copy already there; nothing reaches anyone else, but Jarvis has no uninstall button, so it stays on the phone until you remove it yourself"),\n'
    ),
    why="the app builder's approval cards are unapprovable without these rows",
)

HISTORY_ROUTES = Repair(
    name="history",
    filename="jarvis_hud.py",
    probes=("/api/history/pin", "/api/history/archive"),
    anchor='                     "/api/history/fork", "/api/history/mark"):\n',
    replace_with=(
        '                     "/api/history/fork", "/api/history/mark", "/api/history/pin",\n'
        '                     "/api/history/archive"):\n'
    ),
    why="pinning and archiving a chat answer 404 without these routes",
)

CARD_TIMER = Repair(
    name="timer",
    filename="jarvis_gate.py",
    probes=('d["expires_in"] = _whole', '_waited = d.pop("waited_until", None)'),
    anchor="        # Why this is being asked about at all, when the table said otherwise.\n",
    replace_with=(
        "        # 2026-10-30 (the owner's ruling: \"if there is a card with a limited\n"
        "        # time of any kind, be sure to put the timer on it\"): the request\n"
        "        # that bounds this card is shown to the screens as `expires_in`, in\n"
        "        # whole seconds, only while that request is still waiting. The card\n"
        "        # itself still has no deadline, nothing is refused because a clock\n"
        "        # reached zero, and the 60-second grace is never counted down (no\n"
        "        # request can act in it). Never 0, never negative; the remainder is\n"
        "        # rounded UP so a fraction of a second reads \"1s left\". A ceremony\n"
        "        # card carries no `waited_until` and keeps no timer. `waited_until`\n"
        "        # itself is dropped: the screens are told how long is left, never the\n"
        "        # PC's own clock reading. Copied from backend/show-card-timer.patch.\n"
        "        _waited = d.pop(\"waited_until\", None)\n"
        "        if _waited is not None:\n"
        "            try:\n"
        "                _secs_left = float(_waited) - time.time()\n"
        "            except (TypeError, ValueError):\n"
        "                _secs_left = 0.0\n"
        "            _whole = int(_secs_left)\n"
        "            if _secs_left > _whole:\n"
        "                _whole += 1\n"
        "            if _whole >= 1:\n"
        '                d["expires_in"] = _whole\n'
        "        # Why this is being asked about at all, when the table said otherwise.\n"
    ),
    #: The second half of backend/show-card-timer.patch (its SELECT hunk):
    #: pending() must ask for the column the block above reads. The patch keeps
    #: the SQL valid by splitting the one added string into two literals - the
    #: new column on the first line, `" FROM approvals"` on the second - so this
    #: is exactly that two-line post-image, not a one-line edit (which would
    #: compile and then fail at run time: "raised,waited_until WHERE ..." has no
    #: FROM clause). Without the column `d.pop("waited_until", None)` is always
    #: None - no screen ever gets an `expires_in`, which is a silent no-op this
    #: tool's probes would call applied. Same one write, one backup, one compile.
    extra_edits=(
        ('            "SELECT id,action,tier,detail,prompt,created,raised FROM approvals"\n',
         '            "SELECT id,action,tier,detail,prompt,created,raised,waited_until"\n'
         '            " FROM approvals"\n'),
    ),
    why="a card with a limited life cannot show its timer without both the "
        "inserted block and the SELECT column it reads",
)

UNKNOWN_RISK = Repair(
    name="unknown-risk",
    filename="jarvis_gate.py",
    probes=(
        # One line from each of the six hunks; ALL must be present, so a half
        # applied file is never mistaken for a repaired one. Each is an ADDED
        # line, so none can be present before the repair.
        '"calendar_read": ("yes", "local"',
        'UNCLASSIFIED_WARNING = ("Unclassified action - treated as permanent '
        'and able "',
        '`classified` is False when the table above has no row for `action`.',
        'nobody has written down what it does, so it is given the ',
        'out = dict(_SYNTH_TIERS)',
        'gate.unclassified_forced_ask',
    ),
    why="an action with no risk row must be approvable, and forced to ask",
    lineages=tuple(LIVE_LEGACY_GATES),
    pieces=(
        Piece(
            # The eight rows, FIRST in the table as the patch puts them. Anchored on
            # the opening brace alone, because on this PC the hunk's own two-line
            # pre-image is gone: the #997 `gate` repair inserted the app builder's
            # rows immediately after that brace. The rows are copied from the
            # patch's own post-image, not typed.
            anchor='_RISK: dict[str, tuple[str, str, str]] = {\n',
            replace_with=(
                '_RISK: dict[str, tuple[str, str, str]] = {\n'
                "    # unknown-risk-approvable.patch (Gemini's Q2 ruling, 2026-10-30). These\n"
                '    # EIGHT had an "auto" line in [autonomy.tiers] and NO row here: they were\n'
                '    # the only actions that run with nobody asked while the gate itself calls\n'
                '    # them unclassified. The ruling forces every unclassified action to "ask",\n'
                '    # and these rows are what stops that rule from turning every calendar\n'
                '    # read, mail read, notes search and status check into an approval card.\n'
                '    # Each is the sentence its own tier line already implies - a read, and\n'
                '    # nothing changes - so nothing any screen shows changes today: an "auto"\n'
                '    # action raises no card. What is left of the forced "ask" is aimed at the\n'
                '    # actions nobody has written down at all.\n'
                '    #\n'
                '    # The ninth one of that shape is `lower_api_limit`, and it is NOT here on\n'
                '    # purpose: chatbot-limits.patch already gives it a row, and a second row\n'
                '    # would be dead code - the LAST one wins - which\n'
                '    # backend/test_gate_risk_words.py fails. They sit FIRST in the table, with\n'
                "    # the other reads, and that is also the placement that works: the table's\n"
                '    # END is different on a PC whose patch stack has run and on one where it\n'
                '    # has not (chatbot-limits.patch writes rows there), while these lines are\n'
                '    # the same in both.\n'
                '    "calendar_read": ("yes", "local", "reads your calendar on this PC; changes nothing in it"),\n'
                '    "email_read": ("yes", "local", "reads your mail on this PC through your own account; sends nothing and changes nothing"),\n'
                '    "notes_search": ("yes", "local", "searches your notes on this PC; changes nothing in them"),\n'
                '    "home_read": ("yes", "local", "asks the home devices you set up on your own network for their state; switches nothing"),\n'
                '    "news_read": ("yes", "outbound", "fetches the news feeds you chose; a public read that changes nothing"),\n'
                '    "page_read": ("yes", "outbound", "reads the one page you already named; that site sees this PC\'s address, and nothing changes"),\n'
                '    "github_read": ("yes", "outbound", "reads public GitHub data; sends nothing of yours and changes nothing"),\n'
                '    "docker_service_stop": ("yes", "local", "stops a service you started on this PC; starting it again is its own card"),\n'
                ''
            ),
        ),
        Piece(
            # `UNCLASSIFIED_WARNING` and the worst-case fallback it becomes.
            anchor=(
                '\n'
                '_UNKNOWN_RISK = ("no", "outbound",\n'
                '                 "not classified, so treated as irreversible and outbound")\n'
                '\n'
                '\n'
                'def risk_for(action: str) -> dict:'
            ),
            replace_with=(
                '\n'
                "#: What the card says when the gate has NO row for the action. Gemini's ruling\n"
                '#: of 2026-10-30 asks for it in plain words, and these are they: the action is\n'
                '#: given the worst case this gate has - it cannot be undone, and it can leave\n'
                '#: this PC - and the owner may still say yes, with the human check every risky\n'
                '#: card already needs. ONE sentence, used by `risk_for` and `notice_for`, so\n'
                "#: the card's warning line and its body cannot drift apart.\n"
                'UNCLASSIFIED_WARNING = ("Unclassified action - treated as permanent and able "\n'
                '                        "to leave this PC")\n'
                '\n'
                '_UNKNOWN_RISK = ("no", "outbound", UNCLASSIFIED_WARNING)\n'
                '\n'
                '\n'
                'def risk_for(action: str) -> dict:'
            ),
        ),
        Piece(
            # `risk_for`'s docstring: what `classified: false` now means.
            anchor=(
                '    decisions. The rest is there so a UI can EXPLAIN the decision rather than\n'
                '    just enforce it - a card that says "no undo: there is no unsend" teaches\n'
                '    the rule, and a card that silently refuses a swipe does not.\n'
                '    """\n'
                '    rev, reach, why = _RISK.get(action or "", _UNKNOWN_RISK)\n'
                '    return {'
            ),
            replace_with=(
                '    decisions. The rest is there so a UI can EXPLAIN the decision rather than\n'
                '    just enforce it - a card that says "no undo: there is no unsend" teaches\n'
                '    the rule, and a card that silently refuses a swipe does not.\n'
                '\n'
                '    `classified` is False when the table above has no row for `action`. Since\n'
                "    Gemini's ruling of 2026-10-30 that is not a refusal: the action is given\n"
                '    the worst case the table has (reversible "no", reach "outbound", so no\n'
                '    swipe), its `why` is UNCLASSIFIED_WARNING - the plain warning line every\n'
                '    card shows - and the owner may still approve it, through the same human\n'
                "    check (Windows Hello on this PC, the phone's own lock) every risky card\n"
                '    needs. `check()` is the other half: it forces such an action to tier\n'
                '    "ask", so it can never run unattended.\n'
                '    """\n'
                '    rev, reach, why = _RISK.get(action or "", _UNKNOWN_RISK)\n'
                '    return {'
            ),
        ),
        Piece(
            # `notice_for`: the body says WHY the worst case was chosen.
            anchor=(
                '    heavy = (r["reversible"] == "no") or (r["reach"] != "local") or raised\n'
                '\n'
                '    bits = [r["why"]]\n'
                '    if raised:\n'
                '        # Said, never quoted. That something tried to rush you is the fact that\n'
                '        # changes your decision; its actual words are not needed to convey it,'
            ),
            replace_with=(
                '    heavy = (r["reversible"] == "no") or (r["reach"] != "local") or raised\n'
                '\n'
                '    bits = [r["why"]]\n'
                '    if not r["classified"]:\n'
                '        # The warning line above is the headline; this says WHY the worst case\n'
                "        # was chosen, in the plainest words there are. Both are this file's own\n"
                '        # strings, so the notice is still safe by construction on a lock screen\n'
                '        # (see the docstring above): nothing here reads the payload.\n'
                '        bits.append("nobody has written down what it does, so it is given the "\n'
                '                    "worst case")\n'
                '    if raised:\n'
                '        # Said, never quoted. That something tried to rush you is the fact that\n'
                '        # changes your decision; its actual words are not needed to convey it,'
            ),
        ),
        Piece(
            # DEF-021 (2026-10-31): `_tiers()` lets the owner's explicit
            # `[autonomy.tiers]` line win over `_SYNTH_TIERS`, and the new
            # `_file_tier_names()` beside it is what check()'s forced-ask
            # exemption reads. Its anchor is the owner's OLD function alone; the
            # patch's context around it is dropped, so the same piece applies to
            # the published pre-image, the live gate and the test's synthetic
            # gate. This is the patch's SIXTH hunk (the hunk before the revised
            # check() block below).
            anchor=(
                'def _tiers(framework: Optional[dict] = None) -> dict:\n'
                '    """The tier table, validated. An unrecognised tier string - "Never" with a\n'
                '    capital, "aks", anything not in _VALID_TIERS - is treated as "never",\n'
                '    because a typo in a security policy should lock, not unlock."""\n'
                '    try:\n'
                '        f = framework if framework is not None else fw.load_framework()\n'
                '        raw = f.get("autonomy", {}).get("tiers", {}) or {}\n'
                '    except Exception:\n'
                '        return {}\n'
                '    out = {}\n'
                '    for k, v in raw.items():\n'
                '        v = str(v).strip().lower()\n'
                '        out[k] = v if v in _VALID_TIERS else "never"\n'
                '    out.update(_SYNTH_TIERS)\n'
                '    return out'
            ),
            replace_with=(
                'def _tiers(framework: Optional[dict] = None) -> dict:\n'
                '    """The tier table, validated, with the owner\'s explicit line winning.\n'
                '\n'
                '    An unrecognised tier string - "Never" with a capital, "aks", anything not\n'
                '    in _VALID_TIERS - is treated as "never", because a typo in a security\n'
                '    policy should lock, not unlock.\n'
                '\n'
                '    THE FILE WINS OVER THE TOOL TABLE (DEF-021, 2026-10-31). `_SYNTH_TIERS`\n'
                "    holds the gate's own per-tool defaults for names that are not actions of\n"
                '    [autonomy.tiers] ("calculator" -> auto, "memory_store" -> notify). It used\n'
                '    to be applied AFTER the file, so an owner who wrote a line for one of\n'
                "    those names had it silently overwritten - and `check()`'s forced-ask\n"
                "    exemption then skipped exactly those names. The owner's file is the\n"
                '    policy: its validated line is laid over the synthesised table, so what the\n'
                '    What-asks-first page already showed is what the gate now does. A name with\n'
                '    no file line still takes its synthesised tier unchanged."""\n'
                '    try:\n'
                '        f = framework if framework is not None else fw.load_framework()\n'
                '        raw = f.get("autonomy", {}).get("tiers", {}) or {}\n'
                '    except Exception:\n'
                '        return {}\n'
                '    out = dict(_SYNTH_TIERS)\n'
                '    for k, v in raw.items():\n'
                '        v = str(v).strip().lower()\n'
                '        out[k] = v if v in _VALID_TIERS else "never"\n'
                '    return out\n'
                '\n'
                '\n'
                'def _file_tier_names(framework: Optional[dict] = None) -> set:\n'
                '    """The actions with an EXPLICIT line in the file\'s [autonomy.tiers].\n'
                '\n'
                "    Used by `check()`'s forced-ask rule (DEF-021): the tool-table exemption\n"
                '    applies only when the owner has NOT written a line for that name. A name\n'
                "    the file names is the owner's own action and takes the ordinary rule, so\n"
                '    an unclassified one is still forced to "ask"; a name the file does not\n'
                "    name keeps the gate's per-tool default. Never raises; an unreadable file\n"
                '    answers an empty set, which is the stricter direction for every other rule\n'
                '    (the empty tier table itself refuses in `check()`)."""\n'
                '    try:\n'
                '        f = framework if framework is not None else fw.load_framework()\n'
                '        return set((f.get("autonomy", {}) or {}).get("tiers", {}) or {})\n'
                '    except Exception:\n'
                '        return set()'
            ),
        ),
        Piece(
            # `check()`: an action with no row is forced to ask; never untouched.
            # DEF-021 (2026-10-31) revised this block: the tool-table exemption
            # now needs the owner's file to have NO line for the name too. The
            # anchor and the replacement are the patch's own sixth hunk.
            anchor=(
                '            # is no reading of "no policy" under which a tool call is safe.\n'
                '            raise RuntimeError("autonomy tier table is empty")\n'
                '        tier = tiers.get(action, UNKNOWN_TIER)\n'
                '    except Exception as exc:\n'
                '        # Cannot read the policy -> cannot claim the action is permitted.\n'
                '        _audit("gate.policy_unreadable", {"action": action, "error": str(exc)})'
            ),
            replace_with=(
                '            # is no reading of "no policy" under which a tool call is safe.\n'
                '            raise RuntimeError("autonomy tier table is empty")\n'
                '        tier = tiers.get(action, UNKNOWN_TIER)\n'
                "        # AN ACTION WITH NO RISK ROW MAY NOT RUN WITH NOBODY ASKED (Gemini's\n"
                '        # ruling Q2, 2026-10-30). risk_for() already gives such an action the\n'
                '        # worst case it has - permanent and outbound - and this is the other\n'
                '        # half: whatever [autonomy.tiers] says, an action the risk table does\n'
                '        # not know is forced to "ask". "never" is stricter than ask and is left\n'
                '        # exactly as it is. A risk table that cannot be read forces it too.\n'
                '        #\n'
                '        # A TOOL-TABLE NAME IS EXEMPT ONLY WHEN THE FILE DOES NOT NAME IT.\n'
                '        # `_SYNTH_TIERS` holds the TOOLS whose tier `action_for_tool()` sets\n'
                '        # directly from `_TOOL_ACTIONS` ("calculator" -> auto, "memory_store"\n'
                '        # -> notify, "git_commit" -> ask). Those are the gate\'s own per-tool\n'
                '        # decisions, not actions the risk table classifies - forcing them to\n'
                '        # ask would card every calculation and every saved memory, which is\n'
                '        # not what this rule is for. But an owner who writes an explicit\n'
                '        # [autonomy.tiers] line for one of those names has made it their own\n'
                '        # action (DEF-021, 2026-10-31): the file wins over the tool table in\n'
                '        # `_tiers()`, and this rule must agree with that rather than silently\n'
                '        # skipping the name. So the exemption needs BOTH - the name is in the\n'
                '        # tool table AND the file has no line for it. Everything else is\n'
                '        # covered, including an action with no tier line at all (whose\n'
                '        # fallback used to be loosened by `[autonomy] unknown_action_tier` in\n'
                "        # the owner's file).\n"
                '        #\n'
                '        # Nothing that runs unattended today changes: every action the shipped\n'
                '        # config sets to "auto" or "notify" has its own row (the nine that did\n'
                '        # not are added by this patch), so this closes the hole for the NEXT\n'
                '        # action somebody adds without one.\n'
                '        try:\n'
                '            _explicit = _file_tier_names(framework)\n'
                '        except Exception:\n'
                '            _explicit = set()\n'
                '        try:\n'
                '            _forced = (tier != "never"\n'
                '                       and not (isinstance(action, str)\n'
                '                                and action in _SYNTH_TIERS\n'
                '                                and action not in _explicit)\n'
                '                       and not risk_for(action)["classified"])\n'
                '        except Exception:\n'
                '            _forced = tier != "never"\n'
                '        if _forced:\n'
                '            if tier != "ask":\n'
                '                _audit("gate.unclassified_forced_ask", {"action": action, "was": tier})\n'
                '            tier = "ask"\n'
                '    except Exception as exc:\n'
                '        # Cannot read the policy -> cannot claim the action is permitted.\n'
                '        _audit("gate.policy_unreadable", {"action": action, "error": str(exc)})'
            ),
        ),
    ),
)


REPAIRS = {r.name: r for r in (GATE_ROWS, HISTORY_ROUTES, CARD_TIMER,
                              UNKNOWN_RISK)}


class Refused(Exception):
    pass


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _legacy_patch(digest: str) -> Optional[str]:
    """The stored live->#1023 patch for one accepted legacy gate, or None."""
    blob = LIVE_LEGACY_GATES.get(digest)
    if blob is None:
        return None
    return zlib.decompress(base64.b85decode(blob)).decode("utf-8")


def _apply_unified_diff(text: str, patch: str, *, reverse: bool = False) -> str:
    """Apply one of the stored exact-context patches (or reverse it).

    The stored patches were generated against the exact bytes of an accepted
    pre-image, so a mismatch here means this is not that file - it raises
    ValueError and the caller refuses rather than writing.
    """
    lines = text.splitlines(keepends=True)
    shift = 0
    plines = patch.splitlines(keepends=True)
    i = 0
    while i < len(plines):
        line = plines[i]
        if not line.startswith("@@"):
            i += 1
            continue
        fields = line.split(" ")
        old_start = int(fields[1].split(",")[0][1:])
        new_start = int(fields[2].split(",")[0][1:])
        i += 1
        olds, news = [], []
        while i < len(plines) and not plines[i].startswith("@@"):
            op = plines[i]
            if op.startswith(" "):
                olds.append(op[1:])
                news.append(op[1:])
            elif op.startswith("-"):
                olds.append(op[1:])
            elif op.startswith("+"):
                news.append(op[1:])
            i += 1
        if reverse:
            olds, news = news, olds
            old_start = new_start
        pos = old_start - 1 + shift
        if pos < 0:
            pos = 0
        if lines[pos:pos + len(olds)] != olds:
            raise ValueError("stored patch does not match this gate's bytes")
        lines[pos:pos + len(olds)] = news
        shift += len(news) - len(olds)
    return "".join(lines)


def _reverse_unified_diff(text: str, patch: str) -> str:
    """Undo a stored patch (used by the test to rebuild every accepted pre-image)."""
    return _apply_unified_diff(text, patch, reverse=True)


def _live_lineage_state(repair: Repair, text: str) -> Optional[tuple]:
    """None when this is not a live-lineage repair/file; else ("already"|"missing", new).

    A file already at the verified #1023 post-image is the idempotent no-op.
    A listed live-lineage pre-image is repaired to that post-image and the
    result is hash-verified before anything is written. Anything else that is
    large enough to BE the live lineage is refused, naming its hash - never
    guessed.
    """
    if not repair.lineages:
        return None
    digest = _sha256_text(text)
    if digest == LIVE_GATE_TARGET_SHA256:
        return ("already", None)
    patch = _legacy_patch(digest)
    if patch is None:
        if len(text.encode("utf-8")) >= LIVE_LINEAGE_MIN_BYTES:
            raise Refused(
                f"{repair.filename}: this is a live-lineage gate this repair does "
                f"not recognise (sha256 {digest}). Accepted: the 5-hunk #1008 gate "
                f"and the pre-#1008 lineage; nothing was written and the hash is "
                f"not guessed at.")
        return None
    try:
        new = _apply_unified_diff(text, patch)
    except ValueError as exc:
        raise Refused(
            f"{repair.filename}: the accepted gate's bytes are listed by hash but "
            f"the stored patch no longer matches them ({exc}); nothing written"
        ) from exc
    if _sha256_text(new) != LIVE_GATE_TARGET_SHA256:
        raise Refused(
            f"{repair.filename}: putting the listed pre-image back together did not "
            f"produce the verified #1023 post-image; nothing written and nothing "
            f"guessed")
    return ("missing", new)


def read(path: Path) -> str:
    return path.read_bytes().decode("utf-8", errors="strict")


def _anchor_problem(repair: Repair, text: str) -> str:
    """'' when every anchor is there exactly once, else the refusal text.

    A repair can name several places: `pieces` (a multi-region change - the
    unclassified-action rule's six hunks) and `extra_edits` (further exact
    old/new pairs applied in the same write - the card timer's SELECT line). ALL
    of them are checked BEFORE anything is written, so drift in any one region
    refuses the whole repair instead of applying the parts it could find."""
    parts = repair.parts()
    if not parts:
        return (f"{repair.filename}: the repair {repair.name!r} has no anchor; "
                "refusing to guess")
    checks = []
    for index, piece in enumerate(parts, 1):
        where = f" ({index} of {len(parts)} pieces)" if len(parts) > 1 else ""
        checks.append((piece.anchor, f"the anchor for {repair.name!r}{where}"))
    for index, (old, _new) in enumerate(repair.extra_edits, 1):
        checks.append((old, f"the extra edit {index} of {repair.name!r}"))
    for anchor, label in checks:
        if not anchor:
            return f"{repair.filename}: {label} is empty; refusing to guess"
        count = text.count(anchor)
        if count == 1:
            continue
        if count == 0:
            return (f"{repair.filename}: {label} is not there any more. Nothing was "
                    "written; this install has drifted further and needs a real look.")
        return (f"{repair.filename}: {label} appears {count} times; refusing to guess "
                "which one.")
    return ""


def check_one(live: Path, repair: Repair) -> str:
    """'already' or 'missing'. Raises Refused when the file/anchor is unusable.

    A repair with several hunks (`extra_edits` for the card timer, `pieces` for
    the unclassified-action rule) is ONE change in one file, so a file holding
    only SOME of them is neither 'already' nor safe to insert again - re-running
    the insertion would put a second copy of a block in the live file. That half
    state is REFUSED; the card timer's two hunks (2026-10-30) are why.
    """
    p = live / repair.filename
    if not p.is_file():
        raise Refused(f"{repair.filename} is not in {live} - is this the live backend folder?")
    text = read(p)
    lineage = _live_lineage_state(repair, text)
    if lineage is not None:
        return lineage[0]
    inserted = all(probe in text for probe in repair.probes)
    extras = [replacement in text for _old, replacement in repair.extra_edits]
    if inserted and all(extras):
        return "already"
    if inserted or any(extras):
        raise Refused(
            f"{repair.filename}: the {repair.name!r} repair is only PARTLY present "
            f"({'the inserted block' if inserted else 'a changed line'} is in, the "
            "rest is not). Refusing rather than writing it again and duplicating "
            "code; look at the file by hand.")
    problem = _anchor_problem(repair, text)
    if problem:
        raise Refused(problem)
    return "missing"


def apply_one(live: Path, repair: Repair, *, stamp: str) -> str:
    """Apply the repair's hunks in one write, compiling before the swap sticks."""
    p = live / repair.filename
    state = check_one(live, repair)
    if state == "already":
        return "already"
    text = read(p)
    lineage = _live_lineage_state(repair, text)
    if lineage is not None and lineage[0] == "missing":
        new = lineage[1]
    else:
        new = text
        for piece in repair.parts():
            new = new.replace(piece.anchor, piece.replace_with, 1)
        for old, replacement in repair.extra_edits:
            new = new.replace(old, replacement, 1)
    backup = p.with_name(p.name + f".before-repair-{stamp}")
    # ONE backup per file per run, holding the file as it was BEFORE this run's
    # first write. This matters now that two repairs write the same file
    # (`timer` and `unknown-risk` both write jarvis_gate.py): if the second one
    # copied the file over this backup, the bytes from before the run would be
    # lost and only an intermediate state kept.
    if not backup.exists():
        shutil.copy2(p, backup)
    fd, tmpname = tempfile.mkstemp(prefix=p.name + ".", suffix=".tmp", dir=str(live))
    try:
        with open(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(new)
        if lineage is not None:
            wrote = Path(tmpname).read_text(encoding="utf-8").replace("\r\n", "\n")
            if _sha256_text(wrote) != LIVE_GATE_TARGET_SHA256:
                raise Refused(
                    f"{repair.filename}: the repair would not land on the verified "
                    f"#1023 post-image; nothing written")
        py_compile.compile(tmpname, doraise=True)
        shutil.move(tmpname, str(p))
    except Exception as exc:
        # Put the original back and remove the temporary, so the live folder is
        # never left in a half-written state.
        try:
            shutil.copy2(backup, p)
        finally:
            Path(tmpname).unlink(missing_ok=True)
        raise Refused(f"{repair.filename}: the repaired file did not compile "
                      f"({type(exc).__name__}); the original was restored") from exc
    return "applied"


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--backend-path", required=True,
                    help="the folder holding the live jarvis_hud.py")
    ap.add_argument("--apply", action="store_true",
                    help="write the repairs (without it this is a check)")
    ap.add_argument("--only", default="", choices=["", *REPAIRS.keys()],
                    help="repair only this one")
    ns = ap.parse_args(argv)
    live = Path(ns.backend_path).expanduser()
    chosen = [REPAIRS[ns.only]] if ns.only else list(REPAIRS.values())
    stamp = time.strftime("%Y%m%d-%H%M%S")
    outcomes = []
    try:
        for repair in chosen:
            state = check_one(live, repair)
            if state == "already":
                print(f"ok       {repair.name}: already present")
                outcomes.append("already")
                continue
            if not ns.apply:
                print(f"MISSING  {repair.name}: {repair.why}")
                outcomes.append("missing")
                continue
            applied = apply_one(live, repair, stamp=stamp)
            print(f"{'applied ' if applied == 'applied' else 'ok      '} {repair.name}: "
                  f"{repair.filename} ({'written, backup kept' if applied == 'applied' else 'already present'})")
            outcomes.append(applied)
    except Refused as exc:
        print(f"REFUSED: {exc}")
        return 2
    if "missing" in outcomes:
        print("\nNothing was changed. Re-run with --apply after reviewing the above.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
