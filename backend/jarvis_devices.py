"""jarvis_devices.py - pairing a phone by QR code, and a key per device.

NEW MODULE, shipped whole. devices.patch adds ONE block to jarvis_hud.py,
right after `_refuse_every_interface(bind)` and BEFORE every module's
`install(..., token_ok=_token_ok, ...)` (owner-check's is the first of
them), plus two lines in jarvis_gate.py's tables. The design, with every
choice and its reason, is docs/PAIRING-DESIGN.md (phase 1 only - phase 2,
the fingerprint-signed yes, is NOT built here). The routes are
docs/JARVIS-API.md section 90.

THE OWNER'S DECISIONS (CLAUDE.md, 2026-09-24, and "build QR-code pairing
now", 2026-09-28): a QR code with a short typed code as the backup; an
approval card on the PC before any key is handed over; a key per device,
listed in both apps with its own Remove.

WHAT THIS MODULE DOES
  1. Checks every request's key (`wrap_token_ok`, design 5.2). A device key
     (`jdk1.<id>.<secret>`) is checked against the registry here and NEVER
     falls through to the old check. Anything else goes to the owner's own
     `_token_ok`, unchanged - today's rule - and then, only if the old
     shared key has been retired, is refused from any device but this PC.
  2. Keeps the device registry: `<settings folder>/devices/registry.json`,
     holding a SHA-256 of each key, never the key (design section 4). In a
     subfolder on purpose: backups copy only `*.json` directly in the
     settings folder, so a restore can never bring back a removed key.
  3. Runs ONE pairing session at a time (design section 3): the QR text,
     the typed code, 3 tries, 10 minutes, the four words, the approval card
     `pair_device` (PC only, always Windows Hello - jarvis_owner_check.
     PC_ONLY_ACTIONS), and the key handed over once.
  4. Removing a device cuts off its open connections too (design 5.4): a
     request made with a device key gets a thin guard round `wfile` that
     refuses to write once that device is removed.
  5. The old shared key's Retire (immediate) and Bring back (a card,
     `unretire_shared_key`, PC only, Windows Hello; refused under Lockdown).

FAILING SAFE MEANS TODAY'S BEHAVIOUR, NEVER A LOCK-OUT
  * Without this module (or if devices.patch's block fails), only the
    shared key works - exactly as before. A device key is then refused.
  * A registry file that cannot be read refuses every device key and treats
    the shared key as retired FOR OTHER DEVICES ONLY - this PC always keeps
    working, so the owner can see what is wrong. `--start-fresh` (below)
    moves the bad file aside.
  * Retire cannot cut off the device asking for it (409 uses_it_yourself),
    and never touches this PC.

SECRETS
The pairing secret and the typed code never travel over the network (only
HMAC sums of them do). The QR text and the code appear in ONE answer only -
POST /api/pair/start's, to this PC - never in GET /api/pair/session, an
event, an error or the log. A device key is given out once, by POST
/api/pair/collect, and only its SHA-256 is written anywhere. Nothing here
prints or logs a key, a secret or a code; each is also handed to
jarvis_scrub.register_secret() while it exists, and jarvis_scrub knows the
device key's shape (`jdk1.d<8 hex>.<43>`).

WHAT IT DOES NOT FIX (said plainly, as the design does)
A program already running as the owner on the PC can still read this PC's
key and edit this registry (docs/ARCHITECTURE.md section 3, "A known
limit"). What changes: a copied phone key can be removed on its own, and
the old shared key stops working from other devices once retired.

Standard library only (phase 1 needs no `cryptography`).

    python jarvis_devices.py                 what is paired, and whether pairing works
    python jarvis_devices.py --start-fresh   move an unreadable registry aside
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import sys
import threading
import time
import unicodedata
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlsplit

# ---------------------------------------------------------------------------
# Names and numbers (design sections 5, 6 and 8)
# ---------------------------------------------------------------------------

#: The approval card for a new device. jarvis_owner_check.PC_ONLY_ACTIONS
#: holds the same name: always Windows Hello, never approved from elsewhere.
ACTION = "pair_device"
#: The approval card for bringing the old shared key back for other devices
#: (a loosening). Also in PC_ONLY_ACTIONS.
UNRETIRE_ACTION = "unretire_shared_key"

KEY_PREFIX = "jdk1."
#: The device key's shape, used by the scrubbers and the shared cases file.
KEY_PATTERN = r"jdk1\.d[0-9a-f]{8}\.[A-Za-z0-9_-]{43}"
_KEY_RE = re.compile(r"jdk1\.(d[0-9a-f]{8})\.[A-Za-z0-9_-]{43}")
_ID_RE = re.compile(r"d[0-9a-f]{8}")
_HEX64 = re.compile(r"[0-9a-f]{64}")

SESSION_SECONDS = 600
TRIES = 3
#: last_seen (and the shared key's last use from another device) is written
#: at most this often per device - not on every request.
SEEN_EVERY = 60

QR_SCHEME = "jarvis-pair:"
QR_VERSION = "1"
#: Crockford's alphabet: 0-9 and A-Z without I, L, O and U.
CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
CODE_SALT = b"jarvis-pair-code-v1"
PROOF_LABEL = "jarvis-pair-v1"
NAME_MAX = 40
_NAME_EXTRA = frozenset(" -_.'()")

#: What the phone can use: Tailscale's and NordVPN Meshnet's names only
#: (jarvis-client data/PhoneAddress.kt, network_security_config.xml).
PHONE_SUFFIXES = (".ts.net", ".nord")
_HOST_RE = re.compile(r"[a-z0-9.-]{1,253}")

#: Every state a session can be in (design section 3).
LIVE_STATES = ("waiting_for_phone", "waiting_for_card", "approved")
END_STATES = ("done", "denied", "timed_out", "expired", "burnt", "cancelled", "refused")

# ---------------------------------------------------------------------------
# The words. Both apps show these; tools/gen_pairing_cases.py puts every one
# in the shared cases file so the three cannot drift.
# ---------------------------------------------------------------------------

PC_ONLY = "This can only be done on the PC itself."

#: The phone's sentences, keyed by the answer's `reason` (or `state`).
PHONE_WORDS = {
    "not_mesh": ("Pairing only works over Tailscale or NordVPN Meshnet. Turn one on, "
                 "on this phone and on your PC."),
    "this_pc": "Pairing is for another device - this PC already has its own key.",
    "wrong_proof": "That code is not right. {n} tries left.",
    "wrong_proof_one": "That code is not right. 1 try left.",
    "wrong_proof_none": "Three wrong tries - this code no longer works. Start again on your PC.",
    "gone": "This code no longer works. On your PC, press Pair a phone again.",
    "name": "Use a shorter name, with letters and numbers only.",
    "bad_request": "That pairing request could not be read. Start again on your PC.",
    "card": "Your PC could not show the approval card. Try again.",
    "words_differ": ("The PC answered with different words. Do not approve the card on "
                     "your PC."),
    "waiting": "Approve the card on your PC if it shows these same words.",
    "denied": "You said no on your PC. Nothing changed on this phone.",
    "collect_gone": ("The card on your PC ran out of time or was cancelled. Start again on "
                     "the PC."),
    "qr_invalid": "That is not a Jarvis pairing code.",
    "qr_newer": "This code is from a newer Jarvis - update the app.",
    "code_invalid": "The code is 8 letters and numbers, like K7QM-4TXD.",
    "camera": ("Jarvis uses the camera only to read the code on your PC. Nothing is "
               "recorded or sent."),
}

#: Why a key was refused (design 5.3) - added to the 401 as `"key"`.
KEY_WORDS = {
    "device_removed": ("This phone's key was removed on your PC, so Jarvis no longer "
                       "answers it. Pair again with the QR code in Settings, Devices, on "
                       "your PC."),
    "shared_retired": ("This phone was using the old shared key, which has been retired on "
                       "your PC. Pair it with the QR code in Settings, Devices, on your PC."),
}

#: GET /api/pair/session's `message`, by state. {words} and {name} filled in.
SESSION_WORDS = {
    "waiting_for_phone": "Waiting for your phone...",
    "waiting_for_card": "Your phone asked. Check the card - the words must match: {words}",
    "approved": "Approved. Waiting for {name} to collect its key...",
    "done": "{name} is connected.",
    "denied": "You said no on the card, so {name} was not connected.",
    "timed_out": "Nobody answered the card in time, so nothing was connected. Start again.",
    "expired": "This code ran out of time - it works for 10 minutes. Start again.",
    "burnt": "Three wrong tries - this code no longer works. Start again.",
    "cancelled": "Pairing was cancelled, so nothing was connected.",
    "refused": "The card could not be approved on this PC ({why}), so nothing was connected. "
               "Start again.",
}

#: The Devices page's own sentences (design 7.1 and 7.2).
DEVICES_WORDS = {
    "remove_confirm": ("Remove {name}? It stops reaching Jarvis at once. To use it again, "
                       "pair it again with the QR code."),
    "remove_self": ("This phone will stop reaching Jarvis at once and go back to the pairing "
                    "screen."),
    "uses_it_yourself": ("This phone is still using the old shared key. Pair it with the QR "
                         "code first, or it would cut itself off."),
    "shared_row": ("Old shared key - used by this PC, and by devices paired before "
                   "per-device keys."),
    "shared_retired": "Retired - it now works on this PC only.",
    "unretire_waiting": ("Waiting for your approval. Other devices can use the old shared "
                         "key again only if you approve the card, on this PC."),
    "registry_unreadable": (
        "The device list on this PC cannot be read (devices/registry.json in the Jarvis "
        "settings folder), so no device key works and only this PC can reach Jarvis. To "
        "start fresh, run  py -3 jarvis_devices.py --start-fresh  on the PC - every phone "
        "then pairs again."),
    "no_owner_check": (
        "This PC does not check approvals itself yet (jarvis_owner_check.py is not "
        "running), so a pairing card could never be approved. Run apply-patches.ps1 "
        "again."),
    "tier": ("pair_device is not set to \"ask\" in jarvis-framework.toml, so a pairing card "
             "cannot be raised."),
}

#: The start route's address sentences - the phone's own, word for word:
#: tools/gen_own_network_cases.py PHONE_MESSAGE (off the owner's networks)
#: and jarvis-client data/PhoneAddress.kt MESSAGE (on them, but not a name
#: the phone can reach). test_devices.py checks they match.
ADDRESS_OFF_NETWORK = ("Jarvis's address {address} is not on your own networks, so this app "
                       "will not send your pairing key there: on this phone, use your PC's "
                       "Tailscale name (ending in .ts.net) or its NordVPN Meshnet name "
                       "(ending in .nord).")
ADDRESS_NOT_A_NAME = ("Jarvis's address {address} is on your own network, but this phone can "
                      "only reach your PC by its Tailscale name (ending in .ts.net) or its "
                      "NordVPN Meshnet name (ending in .nord), not by a number or a "
                      "home-network name: type the name the Tailscale or NordVPN app shows "
                      "for your PC.")

CARD_TITLE = "Jarvis wants to connect a new device"

UNRETIRE_CARD_TEXT = "\n".join([
    "Let devices that still have the old shared key reach Jarvis again.",
    "",
    "Right now the old shared key works on this PC only. Approving lets any device on your "
    "Tailscale or NordVPN Meshnet that has it talk to Jarvis again - including a copy of it "
    "someone else may have made.",
    "",
    "Pairing each phone with the QR code (Settings, Devices) is safer: each gets its own "
    "key, which you can remove on its own.",
    "",
    "You can retire it again at any time, and that is instant.",
    "",
    "If you say no: the old shared key keeps working on this PC only.",
])

# ---------------------------------------------------------------------------
# The word list: the EFF "short word list 2" (1,296 words, each with a unique
# first three letters). Creative Commons Attribution 3.0 US, (c) Electronic
# Frontier Foundation - THIRD-PARTY-NOTICES.txt. The same list, word for
# word, is contract/pair-words.txt; test_pairing_cases.py checks the two.
# ---------------------------------------------------------------------------

_WORDS_TEXT = """
aardvark abandoned abbreviate abdomen abhorrence abiding abnormal abrasion
absorbing abundant abyss academy accountant acetone achiness acid acoustics
acquire acrobat actress acuteness aerosol aesthetic affidavit afloat afraid
aftershave again agency aggressor aghast agitate agnostic agonizing agreeing
aidless aimlessly ajar alarmclock albatross alchemy alfalfa algae aliens
alkaline almanac alongside alphabet already also altitude aluminum always
amazingly ambulance amendment amiable ammunition amnesty amoeba amplifier
amuser anagram anchor android anesthesia angelfish animal anklet announcer
anonymous answer antelope anxiety anyplace aorta apartment apnea apostrophe
apple apricot aquamarine arachnid arbitrate ardently arena argument
aristocrat armchair aromatic arrowhead arsonist artichoke asbestos ascend
aseptic ashamed asinine asleep asocial asparagus astronaut asymmetric atlas
atmosphere atom atrocious attic atypical auctioneer auditorium augmented
auspicious automobile auxiliary avalanche avenue aviator avocado awareness
awhile awkward awning awoke axially azalea babbling backpack badass bagpipe
bakery balancing bamboo banana barracuda basket bathrobe bazooka blade
blender blimp blouse blurred boatyard bobcat body bogusness bohemian boiler
bonnet boots borough bossiness bottle bouquet boxlike breath briefcase broom
brushes bubblegum buckle buddhist buffalo bullfrog bunny busboy buzzard
cabin cactus cadillac cafeteria cage cahoots cajoling cakewalk calculator
camera canister capsule carrot cashew cathedral caucasian caviar ceasefire
cedar celery cement census ceramics cesspool chalkboard cheesecake chimney
chlorine chopsticks chrome chute cilantro cinnamon circle cityscape civilian
clay clergyman clipboard clock clubhouse coathanger cobweb coconut codeword
coexistent coffeecake cognitive cohabitate collarbone computer confetti
copier cornea cosmetics cotton couch coverless coyote coziness crawfish
crewmember crib croissant crumble crystal cubical cucumber cuddly cufflink
cuisine culprit cup curry cushion cuticle cybernetic cyclist cylinder cymbal
cynicism cypress cytoplasm dachshund daffodil dagger dairy dalmatian
dandelion dartboard dastardly datebook daughter dawn daytime dazzler dealer
debris decal dedicate deepness defrost degree dehydrator deliverer democrat
dentist deodorant depot deranged desktop detergent device dexterity diamond
dibs dictionary diffuser digit dilated dimple dinnerware dioxide diploma
directory dishcloth ditto dividers dizziness doctor dodge doll dominoes
donut doorstep dorsal double downstairs dozed drainpipe dresser driftwood
droppings drum dryer dubiously duckling duffel dugout dumpster duplex
durable dustpan dutiful duvet dwarfism dwelling dwindling dynamite dyslexia
eagerness earlobe easel eavesdrop ebook eccentric echoless eclipse ecosystem
ecstasy edged editor educator eelworm eerie effects eggnog egomaniac
ejection elastic elbow elderly elephant elfishly eliminator elk elliptical
elongated elsewhere elusive elves emancipate embroidery emcee emerald
emission emoticon emperor emulate enactment enchilada endorphin energy
enforcer engine enhance enigmatic enjoyably enlarged enormous enquirer
enrollment ensemble entryway enunciate envoy enzyme epidemic equipment
erasable ergonomic erratic eruption escalator eskimo esophagus espresso
essay estrogen etching eternal ethics etiquette eucalyptus eulogy euphemism
euthanize evacuation evergreen evidence evolution exam excerpt exerciser
exfoliate exhale exist exorcist explode exquisite exterior exuberant fabric
factory faded failsafe falcon family fanfare fasten faucet favorite feasibly
february federal feedback feigned feline femur fence ferret festival
fettuccine feudalist feverish fiberglass fictitious fiddle figurine fillet
finalist fiscally fixture flashlight fleshiness flight florist flypaper
foamless focus foggy folksong fondue footpath fossil fountain fox fragment
freeway fridge frosting fruit fryingpan gadget gainfully gallstone
gamekeeper gangway garlic gaslight gathering gauntlet gearbox gecko gem
generator geographer gerbil gesture getaway geyser ghoulishly gibberish
giddiness giftshop gigabyte gimmick giraffe giveaway gizmo glasses gleeful
glisten glove glucose glycerin gnarly gnomish goatskin goggles goldfish gong
gooey gorgeous gosling gothic gourmet governor grape greyhound grill
groundhog grumbling guacamole guerrilla guitar gullible gumdrop gurgling
gusto gutless gymnast gynecology gyration habitat hacking haggard haiku
halogen hamburger handgun happiness hardhat hastily hatchling haughty
hazelnut headband hedgehog hefty heinously helmet hemoglobin henceforth
herbs hesitation hexagon hubcap huddling huff hugeness hullabaloo human
hunter hurricane hushing hyacinth hybrid hydrant hygienist hypnotist
ibuprofen icepack icing iconic identical idiocy idly igloo ignition iguana
illuminate imaging imbecile imitator immigrant imprint iodine ionosphere
ipad iphone iridescent irksome iron irrigation island isotope issueless
italicize itemizer itinerary itunes ivory jabbering jackrabbit jaguar
jailhouse jalapeno jamboree janitor jarring jasmine jaundice jawbreaker
jaywalker jazz jealous jeep jelly jeopardize jersey jetski jezebel jiffy
jigsaw jingling jobholder jockstrap jogging john joinable jokingly journal
jovial joystick jubilant judiciary juggle juice jujitsu jukebox jumpiness
junkyard juror justifying juvenile kabob kamikaze kangaroo karate kayak
keepsake kennel kerosene ketchup khaki kickstand kilogram kimono kingdom
kiosk kissing kite kleenex knapsack kneecap knickers koala krypton
laboratory ladder lakefront lantern laptop laryngitis lasagna latch laundry
lavender laxative lazybones lecturer leftover leggings leisure lemon length
leopard leprechaun lettuce leukemia levers lewdness liability library
licorice lifeboat lightbulb likewise lilac limousine lint lioness lipstick
liquid listless litter liverwurst lizard llama luau lubricant lucidity
ludicrous luggage lukewarm lullaby lumberjack lunchbox luridness luscious
luxurious lyrics macaroni maestro magazine mahogany maimed majority makeover
malformed mammal mango mapmaker marbles massager matchstick maverick maximum
mayonnaise moaning mobilize moccasin modify moisture molecule momentum
monastery moonshine mortuary mosquito motorcycle mousetrap movie mower
mozzarella muckiness mudflow mugshot mule mummy mundane muppet mural mustard
mutation myriad myspace myth nail namesake nanosecond napkin narrator
nastiness natives nautically navigate nearest nebula nectar nefarious
negotiator neither nemesis neoliberal nephew nervously nest netting neuron
nevermore nextdoor nicotine niece nimbleness nintendo nirvana nuclear nugget
nuisance nullify numbing nuptials nursery nutcracker nylon oasis oat
obediently obituary object obliterate obnoxious observer obtain obvious
occupation oceanic octopus ocular office oftentimes oiliness ointment older
olympics omissible omnivorous oncoming onion onlooker onstage onward onyx
oomph opaquely opera opium opossum opponent optical opulently oscillator
osmosis ostrich otherwise ought outhouse ovation oven owlish oxford oxidize
oxygen oyster ozone pacemaker padlock pageant pajamas palm pamphlet
pantyhose paprika parakeet passport patio pauper pavement payphone pebble
peculiarly pedometer pegboard pelican penguin peony pepperoni peroxide
pesticide petroleum pewter pharmacy pheasant phonebook phrasing physician
plank pledge plotted plug plywood pneumonia podiatrist poetic pogo poison
poking policeman poncho popcorn porcupine postcard poultry powerboat prairie
pretzel princess propeller prune pry pseudo psychopath publisher pucker
pueblo pulley pumpkin punchbowl puppy purse pushup putt puzzle pyramid
python quarters quesadilla quilt quote racoon radish ragweed railroad
rampantly rancidity rarity raspberry ravishing rearrange rebuilt receipt
reentry refinery register rehydrate reimburse rejoicing rekindle relic
remote renovator reopen reporter request rerun reservoir retriever reunion
revolver rewrite rhapsody rhetoric rhino rhubarb rhyme ribbon riches ridden
rigidness rimmed riptide riskily ritzy riverboat roamer robe rocket romancer
ropelike rotisserie roundtable royal rubber rudderless rugby ruined rulebook
rummage running rupture rustproof sabotage sacrifice saddlebag saffron
sainthood saltshaker samurai sandworm sapphire sardine sassy satchel sauna
savage saxophone scarf scenario schoolbook scientist scooter scrapbook
sculpture scythe secretary sedative segregator seismology selected semicolon
senator septum sequence serpent sesame settler severely shack shelf shirt
shovel shrimp shuttle shyness siamese sibling siesta silicon simmering
singles sisterhood sitcom sixfold sizable skateboard skeleton skies skulk
skylight slapping sled slingshot sloth slumbering smartphone smelliness
smitten smokestack smudge snapshot sneezing sniff snowsuit snugness speakers
sphinx spider splashing sponge sprout spur spyglass squirrel statue
steamboat stingray stopwatch strawberry student stylus suave subway suction
suds suffocate sugar suitcase sulphur superstore surfer sushi swan
sweatshirt swimwear sword sycamore syllable symphony synagogue syringes
systemize tablespoon taco tadpole taekwondo tagalong takeout tallness tamale
tanned tapestry tarantula tastebud tattoo tavern thaw theater thimble thorn
throat thumb thwarting tiara tidbit tiebreaker tiger timid tinsel tiptoeing
tirade tissue tractor tree tripod trousers trucks tryout tubeless tuesday
tugboat tulip tumbleweed tupperware turtle tusk tutorial tuxedo tweezers
twins tyrannical ultrasound umbrella umpire unarmored unbuttoned uncle
underwear unevenness unflavored ungloved unhinge unicycle unjustly unknown
unlocking unmarked unnoticed unopened unpaved unquenched unroll unscrewing
untied unusual unveiled unwrinkled unyielding unzip upbeat upcountry update
upfront upgrade upholstery upkeep upload uppercut upright upstairs uptown
upwind uranium urban urchin urethane urgent urologist username usher utensil
utility utmost utopia utterance vacuum vagrancy valuables vanquished
vaporizer varied vaseline vegetable vehicle velcro vendor vertebrae
vestibule veteran vexingly vicinity videogame viewfinder vigilante village
vinegar violin viperfish virus visor vitamins vivacious vixen vocalist vogue
voicemail volleyball voucher voyage vulnerable waffle wagon wakeup walrus
wanderer wasp water waving wheat whisper wholesaler wick widow wielder
wifeless wikipedia wildcat windmill wipeout wired wishbone wizardry
wobbliness wolverine womb woolworker workbasket wound wrangle wreckage
wristwatch wrongdoing xerox xylophone yacht yahoo yard yearbook yesterday
yiddish yield yo-yo yodel yogurt yuppie zealot zebra zeppelin zestfully
zigzagged zillion zipping zirconium zodiac zombie zookeeper zucchini
"""
WORDS = tuple(_WORDS_TEXT.split())

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64u(text: str) -> Optional[bytes]:
    if not isinstance(text, str) or not re.fullmatch(r"[A-Za-z0-9_-]*", text):
        return None
    try:
        return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except (ValueError, TypeError):
        return None


def _hmac(key: bytes, *parts) -> bytes:
    msg = b"\x00".join(p if isinstance(p, bytes) else str(p).encode("utf-8") for p in parts)
    return hmac.new(key, msg, hashlib.sha256).digest()


def _now() -> float:
    """The clock sessions run on (tests replace it)."""
    return time.monotonic()


def _wall() -> float:
    """Seconds since 1970 (tests replace it)."""
    return time.time()


def _audit(event: str, detail: dict) -> None:
    """An audit line. Ids and states only - never a key, secret, code or hash."""
    try:
        import jarvis_framework as fw
        fw.audit_log(event, detail)
    except Exception:
        pass


def _publish(kind: str, data: dict) -> None:
    try:
        import jarvis_events
        jarvis_events.BUS.publish(kind, data)
    except Exception:
        pass


def _hide(*values) -> None:
    """Keep a secret out of this process's log (jarvis_scrub, layer 1)."""
    try:
        import jarvis_scrub
        for v in values:
            if v:
                jarvis_scrub.register_secret(v)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# The sums (design 6.2) - HMAC-SHA256, base64url without padding
# ---------------------------------------------------------------------------


def normalise_code(text) -> Optional[str]:
    """The typed code as the sums use it: upper case, spaces and "-" gone, O
    read as 0, I and L as 1. None unless exactly 8 characters of the
    alphabet remain."""
    if not isinstance(text, str):
        return None
    t = text.upper().replace(" ", "").replace("-", "")
    t = t.replace("O", "0").replace("I", "1").replace("L", "1")
    if len(t) != 8 or any(c not in CODE_ALPHABET for c in t):
        return None
    return t


def show_code(code: str) -> str:
    """K7QM4TXD -> K7QM-4TXD."""
    return f"{code[:4]}-{code[4:]}"


def code_key(code: str) -> bytes:
    """K for method "code": SHA256("jarvis-pair-code-v1" \\0 CODE)."""
    return hashlib.sha256(CODE_SALT + b"\x00" + code.encode("ascii")).digest()


def transcript(method: str, ref: str, phone_nonce: str, name: str) -> bytes:
    """T = "jarvis-pair-v1" \\0 method \\0 ref \\0 phone_nonce \\0 name."""
    return b"\x00".join(s.encode("utf-8") for s in (PROOF_LABEL, method, ref, phone_nonce, name))


def claim_proof(k: bytes, t: bytes) -> str:
    return _b64u(_hmac(k, b"claim", t))


def pc_proof(k: bytes, t: bytes, pc_nonce: str) -> str:
    return _b64u(_hmac(k, b"pc", t, pc_nonce))


def word_numbers(k: bytes, t: bytes, pc_nonce: str) -> list:
    d = _hmac(k, b"words", t, pc_nonce)
    return [(d[2 * i] * 256 + d[2 * i + 1]) % 1296 for i in range(4)]


def words_for(numbers) -> list:
    return [WORDS[n] for n in numbers]


def collect_proof(k: bytes, pair_id: str, phone_nonce: str) -> str:
    return _b64u(_hmac(k, b"collect", pair_id, phone_nonce))


def name_ok(name) -> bool:
    """1-40 characters (Unicode code points): letters and digits of any
    script, space, and - _ . ' ( ). Nothing else - no control or
    right-to-left characters, no line breaks: the name is shown on an
    approval card, so it must not be able to fake the card's words. Refused
    when outside the rule, never cleaned (it is part of the sums)."""
    if not isinstance(name, str) or not 1 <= len(name) <= NAME_MAX:
        return False
    for c in name:
        if c in _NAME_EXTRA:
            continue
        if unicodedata.category(c)[0] not in ("L", "N"):
            return False
    return True


def _nonce_ok(text) -> bool:
    raw = _unb64u(text)
    return isinstance(text, str) and len(text) == 22 and raw is not None and len(raw) == 16


# ---------------------------------------------------------------------------
# The QR text (design 8.4) and the address the desktop gives (6.1)
# ---------------------------------------------------------------------------


def _own_network(host: str) -> bool:
    try:
        import jarvis_local_http
        return bool(jarvis_local_http._own_network(host))
    except Exception:
        return False


def phone_host(address) -> Optional[str]:
    """The address as the QR code carries it, or None when the phone could
    not use it: the shared own-networks rule AND a name ending .ts.net or
    .nord, lower case, [a-z0-9.-], 1-253 characters. One trailing dot is
    dropped; upper case is lowered."""
    if not isinstance(address, str):
        return None
    h = address.strip().lower()
    if h.endswith("."):
        h = h[:-1]
    if not _HOST_RE.fullmatch(h) or not h.endswith(PHONE_SUFFIXES):
        return None
    if h.startswith((".", "-")) or ".." in h:
        return None
    return h if _own_network(h) else None


def address_problem(address) -> str:
    """The phone's own sentence for an address it could not use."""
    shown = address if isinstance(address, str) else ""
    shown = shown.strip()
    unshown = (not shown) or any(c == "@" or c.isspace() or unicodedata.category(c)[0] == "C"
                                 for c in shown)
    host = shown.lower().rstrip(".")
    on_own = bool(shown) and _own_network(host)
    text = ADDRESS_NOT_A_NAME if on_own else ADDRESS_OFF_NETWORK
    return text.replace("{address} ", "") if unshown else text.replace("{address}", shown)


def qr_text(host: str, port: int, pair_id: str, secret: bytes, expires: int) -> str:
    return f"{QR_SCHEME}{QR_VERSION}/{host}/{port}/{pair_id}/{_b64u(secret)}/{expires}"


class QrError(ValueError):
    """`reason` is "newer" (another version) or "invalid"."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def parse_qr(text) -> dict:
    """The QR text, checked the strict way all three apps check it. Raises
    QrError("newer") for a version other than 1, QrError("invalid") for
    anything else that is not exactly the shape."""
    if not isinstance(text, str) or not text.startswith(QR_SCHEME):
        raise QrError("invalid")
    parts = text[len(QR_SCHEME):].split("/")
    if len(parts) != 6:
        raise QrError("invalid")
    version, host, port, pair_id, secret, expires = parts
    if not re.fullmatch(r"[1-9][0-9]{0,8}", version):
        raise QrError("invalid")
    if version != QR_VERSION:
        raise QrError("newer")
    if phone_host(host) != host:
        raise QrError("invalid")
    if not re.fullmatch(r"[1-9][0-9]{0,4}", port) or not 1 <= int(port) <= 65535:
        raise QrError("invalid")
    if not re.fullmatch(r"[0-9a-f]{16}", pair_id):
        raise QrError("invalid")
    raw = _unb64u(secret)
    if len(secret) != 22 or raw is None or len(raw) != 16:
        raise QrError("invalid")
    if not re.fullmatch(r"[0-9]{10}", expires):
        raise QrError("invalid")
    return {"host": host, "port": int(port), "pair_id": pair_id, "secret": raw,
            "expires": int(expires)}


# ---------------------------------------------------------------------------
# Where a request comes from
# ---------------------------------------------------------------------------

_MESH_NETS = (ipaddress.ip_network("100.64.0.0/10"),        # Tailscale and NordVPN Meshnet
              ipaddress.ip_network("fd7a:115c:a1e0::/48"))  # Tailscale IPv6


def _mesh_nets() -> tuple:
    """The two mesh ranges, from jarvis_local_http's own list (one rule)."""
    try:
        import jarvis_local_http
        found = tuple(n for n in jarvis_local_http._OWN_NETS
                      if str(n) in ("100.64.0.0/10", "fd7a:115c:a1e0::/48"))
        if len(found) == 2:
            return found
    except Exception:
        pass
    return _MESH_NETS


def _ip(text):
    try:
        ip = ipaddress.ip_address(str(text or "").split("%", 1)[0].strip("[] "))
    except ValueError:
        return None
    return getattr(ip, "ipv4_mapped", None) or ip


def from_this_pc(peer, local=None, own=None) -> bool:
    """jarvis_owner_check.from_this_pc - the one rule. Without that module:
    loopback, the connection's own address, or anything unplaceable."""
    try:
        import jarvis_owner_check
        return bool(jarvis_owner_check.from_this_pc(peer, local, own))
    except Exception:
        p = _ip(peer)
        if p is None or p.is_loopback or p.is_unspecified:
            return True
        lo = _ip(local)
        return lo is not None and p == lo


def mesh_peer(peer, local=None, own=None) -> str:
    """"mesh" for another of the owner's devices on Tailscale or Meshnet,
    "this_pc" for this PC (even over its own mesh address), "no" else."""
    if from_this_pc(peer, local, own):
        return "this_pc"
    p = _ip(peer)
    if p is not None and any(p.version == n.version and p in n for n in _mesh_nets()):
        return "mesh"
    return "no"


def _peer_local(handler):
    peer = (getattr(handler, "client_address", None) or ("",))[0]
    try:
        local = handler.connection.getsockname()[0]
    except Exception:
        local = None
    return peer, local


# ---------------------------------------------------------------------------
# The registry (design section 4)
# ---------------------------------------------------------------------------


def _config_dir() -> Path:
    """The same folder every other switch here uses, found the same way."""
    fw = sys.modules.get("jarvis_framework")
    if fw is None:
        try:
            import jarvis_framework as fw  # type: ignore
        except Exception:
            fw = None
    if fw is not None:
        try:
            return Path(fw.CONFIG_DIR)
        except Exception:
            pass
    env = os.environ.get("OPENJARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return Path(os.path.expanduser("~")) / ".openjarvis"


def registry_path() -> Path:
    return _config_dir() / "devices" / "registry.json"


def _empty() -> dict:
    return {"version": 1, "devices": [],
            "shared": {"retired": False, "retired_at": None,
                       "last_other_seen": None, "last_other_address": None}}


class Broken(Exception):
    """The registry cannot be read or does not have the right shape."""


def _valid(doc) -> dict:
    if not isinstance(doc, dict) or doc.get("version") != 1:
        raise Broken("version")
    devices = doc.get("devices")
    shared = doc.get("shared")
    if not isinstance(devices, list) or not isinstance(shared, dict):
        raise Broken("shape")
    seen = set()
    for row in devices:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) \
                or not _ID_RE.fullmatch(row["id"]) or row["id"] in seen:
            raise Broken("device id")
        seen.add(row["id"])
        h = row.get("token_sha256")
        if not isinstance(h, str) or not (h == "" or _HEX64.fullmatch(h)):
            raise Broken("device hash")
        if not isinstance(row.get("name"), str):
            raise Broken("device name")
    if not isinstance(shared.get("retired"), bool):
        raise Broken("shared")
    base = _empty()["shared"]
    base.update(shared)
    doc["shared"] = base
    return doc


_REG_LOCK = threading.RLock()
_CACHE: dict = {"stamp": None, "doc": None, "why": ""}


def _stamp(p: Path):
    try:
        st = p.stat()
    except FileNotFoundError:
        return "missing"
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


def load() -> tuple:
    """(registry, why). `why` is "" when it was read (or does not exist yet -
    an empty registry, today's behaviour); otherwise the registry is empty
    and every caller must treat it as broken. Cached until the file
    changes, so a request costs one stat()."""
    p = registry_path()
    with _REG_LOCK:
        stamp = _stamp(p)
        if stamp is not None and stamp == _CACHE["stamp"] and _CACHE["doc"] is not None:
            return _CACHE["doc"], _CACHE["why"]
        if stamp == "missing":
            doc, why = _empty(), ""
        else:
            try:
                doc, why = _valid(json.loads(p.read_text(encoding="utf-8"))), ""
            except (OSError, ValueError, Broken) as exc:
                doc, why = _empty(), f"unreadable ({type(exc).__name__})"
        _CACHE.update(stamp=stamp, doc=doc, why=why)
        return doc, why


def _write(doc: dict) -> None:
    p = registry_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    os.replace(tmp, p)
    _CACHE.update(stamp=_stamp(p), doc=doc, why="")


def _mutate(fn: Callable[[dict], object]):
    """Read, change and write the registry under the lock (a temporary file
    renamed over the old one, so a crash never leaves half a file). Raises
    Broken rather than write over a registry that could not be read."""
    with _REG_LOCK:
        doc, why = load()
        if why:
            raise Broken(why)
        doc = json.loads(json.dumps(doc))        # never change the cached copy in place
        out = fn(doc)
        _write(doc)
        return out


def start_fresh() -> str:
    """Move an unreadable registry aside as registry.json.broken-<time> and
    start an empty one. Every phone then pairs again. Only from this PC's
    command line - there is no route for it."""
    p = registry_path()
    with _REG_LOCK:
        _doc, why = load()
        if not why:
            return "The device list reads fine - nothing was changed."
        aside = p.with_name(f"{p.name}.broken-{int(_wall())}")
        os.replace(p, aside)
        _write(_empty())
    return f"The unreadable device list was moved aside to {aside.name}; every phone pairs again."


def _live_row(doc: dict, device_id: str) -> Optional[dict]:
    for row in doc.get("devices", ()):
        if row.get("id") == device_id and not row.get("removed") and row.get("token_sha256"):
            return row
    return None


def is_live(device_id: str) -> bool:
    """True while `device_id` is paired and not removed. False when the
    registry cannot be read (fail closed for other devices)."""
    try:
        doc, why = load()
    except Exception:
        return False
    return not why and _live_row(doc, device_id) is not None


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def check_device_key(key: str) -> tuple:
    """(device id or None, why refused or None). `why` is "device_removed"
    for a well-formed key whose device is unknown, removed, or holds another
    key; None when the key is malformed or the registry is unreadable
    (nothing is claimed that is not known)."""
    m = _KEY_RE.fullmatch(key or "")
    if not m:
        return None, None
    try:
        doc, why = load()
    except Exception:
        return None, None
    if why:
        return None, None
    row = _live_row(doc, m.group(1))
    if row is None or not hmac.compare_digest(row["token_sha256"], _hash(key)):
        return None, "device_removed"
    return row["id"], None


# ---- last seen, written at most once a minute ----------------------------

_SEEN: dict = {}           # id -> minute last used (memory)
_SEEN_WRITTEN: dict = {}   # id -> when it was last written
_OTHER: dict = {}          # {"at", "address"} - the shared key from another device
_SEEN_LOCK = threading.Lock()


def _minute(t: float) -> int:
    return int(t) // 60 * 60


def _note_seen(device_id: str) -> None:
    now = _wall()
    with _SEEN_LOCK:
        _SEEN[device_id] = _minute(now)
        due = now - _SEEN_WRITTEN.get(device_id, 0.0) >= SEEN_EVERY
        if due:
            _SEEN_WRITTEN[device_id] = now
    if not due:
        return

    def change(doc):
        row = _live_row(doc, device_id)
        if row is not None:
            row["last_seen"] = _minute(now)

    try:
        _mutate(change)
    except Exception:
        pass


def _note_other(address: str) -> None:
    now = _wall()
    with _SEEN_LOCK:
        _OTHER.update(at=_minute(now), address=str(address or ""))
        due = now - _SEEN_WRITTEN.get("shared", 0.0) >= SEEN_EVERY
        if due:
            _SEEN_WRITTEN["shared"] = now
    if not due:
        return

    def change(doc):
        doc["shared"]["last_other_seen"] = _minute(now)
        doc["shared"]["last_other_address"] = str(address or "")

    try:
        _mutate(change)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# The check on every request (design 5.2 - 5.4)
# ---------------------------------------------------------------------------


class _StreamGuard:
    """Round `handler.wfile` for a request made with a device key: every
    write first asks whether that device is still paired, and raises
    BrokenPipeError when it was removed - so an open event stream or a
    streaming answer ends within one keepalive (about 10 s) of Remove.
    Everything else passes straight through."""

    __slots__ = ("_raw", "_h")

    def __init__(self, raw, handler):
        object.__setattr__(self, "_raw", raw)
        object.__setattr__(self, "_h", handler)

    def _check(self):
        dev = getattr(self._h, "_jarvis_guard_device", None)
        if dev and not is_live(dev):
            raise BrokenPipeError("this device was removed on the PC")

    def write(self, data):
        self._check()
        return self._raw.write(data)

    def writelines(self, lines):
        self._check()
        return self._raw.writelines(lines)

    def __getattr__(self, name):
        return getattr(self._raw, name)

    def __setattr__(self, name, value):
        setattr(self._raw, name, value)


def _guard(handler, device_id: Optional[str]) -> None:
    handler._jarvis_guard_device = device_id
    if device_id is None:
        return
    raw = getattr(handler, "wfile", None)
    if raw is not None and not isinstance(raw, _StreamGuard):
        handler.wfile = _StreamGuard(raw, handler)


def _say_why(handler, reason: Optional[str]) -> None:
    """Remember why THIS request's key was refused, and teach this handler's
    `_send` to add `"key": reason` to the 401 the route code writes."""
    try:
        handler._jarvis_key_refusal = (getattr(handler, "headers", None), reason)
        if getattr(handler, "_jarvis_send_wrapped", False):
            return
        original = getattr(handler, "_send", None)
        if original is None:
            return

        def _send(code, obj=None, *args, **kwargs):
            try:
                said = getattr(handler, "_jarvis_key_refusal", None)
                if (code == 401 and said and said[1] and isinstance(obj, dict)
                        and said[0] is getattr(handler, "headers", None) and "key" not in obj):
                    obj = dict(obj, key=said[1])
            except Exception:
                pass
            return original(code, obj, *args, **kwargs)

        handler._send = _send
        handler._jarvis_send_wrapped = True
    except Exception:
        pass


def _header_key(handler) -> str:
    try:
        return str(handler.headers.get("X-Jarvis-Token") or "").strip()
    except Exception:
        return ""


def wrap_token_ok(original: Callable) -> Callable:
    """The owner's `_token_ok(handler)`, with device keys and Retire added
    (design 5.2). Idempotent. Never raises: a device key that cannot be
    checked is refused; anything else that goes wrong falls back to the
    original's own answer - today's behaviour."""
    if getattr(original, "_jarvis_devices", False):
        return original

    def token_ok(handler):
        key = _header_key(handler)
        if key.startswith(KEY_PREFIX):
            try:
                device_id, why = check_device_key(key)
            except Exception:
                device_id, why = None, None
            if device_id is None:
                _say_why(handler, why)
                return False
            try:
                handler._jarvis_device = device_id
                _say_why(handler, None)
                _note_seen(device_id)
                _guard(handler, device_id)
            except Exception:
                pass
            return True
        ok = original(handler)
        if not ok:
            _say_why(handler, None)
            return ok
        try:
            peer, local = _peer_local(handler)
            here = from_this_pc(peer, local)
            if not here:
                doc, why = load()
                if why or doc["shared"]["retired"]:
                    _say_why(handler, None if why else "shared_retired")
                    return False
                _note_other(peer)
            handler._jarvis_device = "pc" if here else "shared"
            _say_why(handler, None)
            _guard(handler, None)
        except Exception:
            pass
        return ok

    token_ok._jarvis_devices = True
    token_ok._jarvis_original = original
    return token_ok


def _who(handler) -> str:
    """"pc", "shared" or a device id - who made this (already checked)
    request."""
    you = getattr(handler, "_jarvis_device", None)
    if isinstance(you, str) and you:
        return you
    peer, local = _peer_local(handler)
    return "pc" if from_this_pc(peer, local) else "shared"


# ---------------------------------------------------------------------------
# Approval cards
# ---------------------------------------------------------------------------


def _gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _tier(action: str) -> str:
    try:
        import jarvis_framework as fw
        return str(fw.action_tier(action))
    except Exception as exc:
        return f"unreadable ({type(exc).__name__})"


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-devices-card", daemon=True).start()


def _owner_check_armed() -> bool:
    try:
        import jarvis_owner_check
        return bool(jarvis_owner_check.armed())
    except Exception:
        return False


def _lockdown_on() -> bool:
    try:
        import jarvis_asks_first
        return bool(jarvis_asks_first.lockdown_on())
    except Exception:
        return False


def _lockdown_words() -> str:
    try:
        import jarvis_asks_first
        return str(jarvis_asks_first.LOCKDOWN_NO_LOOSEN)
    except Exception:
        return ("Lockdown is on, so nothing can be loosened - turn Lockdown off first "
                "(on the PC, with an approval card and Windows Hello).")


def _verdict(v, action: str, tier_of) -> tuple:
    """(outcome, why) from a gate Verdict: "approved" only for a person's yes
    at tier "ask"; "denied", "timed_out" or "refused" otherwise."""
    vtier = getattr(v, "tier", "unknown")
    allowed = getattr(v, "allowed", False) is True
    outcome = getattr(v, "outcome", None)
    if outcome is None:
        outcome = "approved" if (allowed and vtier == "ask") else "refused"
    if vtier != "ask" or tier_of(action) != "ask":
        return "refused", f"the gate answered at tier {vtier!r}, which is not a person saying yes"
    if allowed and outcome == "approved":
        return "approved", ""
    if outcome in ("denied", "timed_out"):
        return outcome, ""
    return "refused", str(getattr(v, "reason", "") or "refused")


def card_text(name: str, words: list) -> str:
    """The pair_device card's words (design 6.3)."""
    return "\n".join([
        f"\"{name}\" is asking for its own key to talk to Jarvis.",
        "Check that phone shows these four words: " + " · ".join(words),
        "",
        "Approve only if you are pairing that phone right now, on this PC. If you did not "
        "press \"Pair a phone\", deny this. You can remove the device any time in Settings, "
        "Devices.",
    ])


def why_not(tier_of: Optional[Callable] = None, armed: Optional[Callable] = None) -> Optional[str]:
    """A sentence when pairing cannot work on this PC, else None. Windows
    Hello not being set up is found only when the card is approved
    (jarvis_owner_check refuses it then, with its own sentence) - there is
    no way to ask Windows without showing the prompt."""
    tier_of = tier_of or _tier
    armed = armed or _owner_check_armed
    _doc, why = load()
    if why:
        return DEVICES_WORDS["registry_unreadable"]
    if tier_of(ACTION) != "ask":
        return DEVICES_WORDS["tier"]
    if not armed():
        return DEVICES_WORDS["no_owner_check"]
    return None


# ---------------------------------------------------------------------------
# The pairing session (design sections 3 and 6.1 - 6.3)
# ---------------------------------------------------------------------------


class Session:
    def __init__(self, *, host: str, port: int):
        self.pair_id = secrets.token_hex(8)
        self.secret = secrets.token_bytes(16)
        self.code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
        self.pc_nonce = _b64u(secrets.token_bytes(16))
        self.started = _now()
        self.expires = self.started + SESSION_SECONDS
        self.expires_wall = int(_wall()) + SESSION_SECONDS
        self.host, self.port = host, port
        self.state = "waiting_for_phone"
        self.tries_left = TRIES
        self.wrong_from: list = []
        self.method: Optional[str] = None
        self.phone_nonce: Optional[str] = None
        self.name: Optional[str] = None
        self.words: Optional[list] = None
        self.why = ""
        self.device_id: Optional[str] = None
        _hide(_b64u(self.secret), self.code, show_code(self.code), self.qr())

    def qr(self) -> str:
        return qr_text(self.host, self.port, self.pair_id, self.secret, self.expires_wall)

    def key(self, method: Optional[str] = None) -> bytes:
        method = method or self.method
        return self.secret if method == "qr" else code_key(self.code)

    def ref(self, method: Optional[str] = None) -> str:
        return self.pair_id if (method or self.method) == "qr" else "-"

    def expires_in(self) -> int:
        return max(0, int(self.expires - _now() + 0.999))


_LOCK = threading.Lock()
_S: dict = {"session": None}
#: A few ended sessions' final states, so a late phone hears "expired" or
#: "cancelled" rather than "none".
_ENDED: dict = {}
_ENDED_MAX = 8


def _end(s: Session, state: str, why: str = "") -> None:
    """Called under _LOCK."""
    if s.state in END_STATES:
        return
    s.state = state
    s.why = why
    _ENDED[s.pair_id] = state
    while len(_ENDED) > _ENDED_MAX:
        del _ENDED[next(iter(_ENDED))]
    _audit("devices.pair", {"state": state})


def _tick() -> Optional[Session]:
    """The current session, ended as `expired` once its 10 minutes are up.
    Called under _LOCK."""
    s = _S["session"]
    if s is not None and s.state in LIVE_STATES and _now() >= s.expires:
        _end(s, "expired")
    return s


def _reset_for_tests() -> None:
    with _LOCK:
        _S["session"] = None
        _ENDED.clear()
    with _U_LOCK:
        _U.clear()
        _U_WITHDRAWN.clear()
        _U_LAST.clear()
    with _SEEN_LOCK:
        _SEEN.clear()
        _SEEN_WRITTEN.clear()
        _OTHER.clear()
    with _REG_LOCK:
        _CACHE.update(stamp=None, doc=None, why="")


def start(body, *, here: bool, default_port: Optional[int] = None,
          tier_of: Optional[Callable] = None, armed: Optional[Callable] = None) -> tuple:
    """POST /api/pair/start. (http code, body)."""
    if not here:
        return 403, {"ok": False, "pc_only": True, "error": PC_ONLY}
    if not isinstance(body, dict):
        return 400, {"ok": False, "reason": "bad_request", "error": "need a JSON object"}
    address = body.get("address")
    host = phone_host(address)
    if host is None:
        return 400, {"ok": False, "reason": "address", "error": address_problem(address)}
    port = body.get("port", default_port)
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        return 400, {"ok": False, "reason": "bad_request",
                     "error": "port must be a whole number from 1 to 65535"}
    problem = why_not(tier_of, armed)
    if problem:
        return 503, {"ok": False, "error": problem}
    with _LOCK:
        old = _tick()
        if old is not None and old.state in LIVE_STATES:
            _end(old, "cancelled", "a new pairing was started")
        s = Session(host=host, port=port)
        _S["session"] = s
        out = {"ok": True, "pair_id": s.pair_id, "qr": s.qr(), "code": show_code(s.code),
               "expires_in": SESSION_SECONDS, "tries_left": s.tries_left}
    _audit("devices.pair", {"state": "started"})
    return 200, out


def _message(s: Session) -> str:
    text = SESSION_WORDS.get(s.state, "")
    return (text.replace("{words}", " · ".join(s.words or []))
            .replace("{name}", s.name or "The phone")
            .replace("{why}", s.why or "refused"))


def session_view(*, here: bool) -> tuple:
    """GET /api/pair/session. Never the QR text, the secret or the code."""
    if not here:
        return 403, {"ok": False, "pc_only": True, "error": PC_ONLY}
    with _LOCK:
        s = _tick()
        if s is None:
            return 200, {"state": "none"}
        live = s.state in LIVE_STATES
        return 200, {"state": s.state, "expires_in": s.expires_in() if live else 0,
                     "tries_left": s.tries_left, "device_name": s.name,
                     "words": list(s.words) if s.words else None,
                     "wrong_tries_from": list(s.wrong_from), "message": _message(s)}


def cancel(*, here: bool) -> tuple:
    """POST /api/pair/cancel. A waiting card is withdrawn: approving it
    afterwards makes no key."""
    if not here:
        return 403, {"ok": False, "pc_only": True, "error": PC_ONLY}
    with _LOCK:
        s = _tick()
        if s is None:
            return 200, {"ok": True, "was": "none"}
        was = s.state
        if was in LIVE_STATES:
            _end(s, "cancelled", "you pressed Cancel")
    return 200, {"ok": True, "was": was}


def _wrong(s: Session, peer: str) -> tuple:
    """Count one wrong try (under _LOCK). At none left the session is burnt,
    and a card still waiting is withdrawn."""
    s.tries_left = max(0, s.tries_left - 1)
    if peer and peer not in s.wrong_from and len(s.wrong_from) < 10:
        s.wrong_from.append(str(peer))
    if s.tries_left == 0:
        _end(s, "burnt", "three wrong tries")
        words = PHONE_WORDS["wrong_proof_none"]
    elif s.tries_left == 1:
        words = PHONE_WORDS["wrong_proof_one"]
    else:
        words = PHONE_WORDS["wrong_proof"].replace("{n}", str(s.tries_left))
    return 403, {"ok": False, "reason": "wrong_proof", "tries_left": s.tries_left,
                 "error": words}


def _gone_state(s: Optional[Session], pair_id=None, *, for_collect=False) -> str:
    """The `state` a 410 names. Claim: expired | burnt | cancelled | used |
    none. Collect: timed_out | expired | cancelled | refused | used | none."""
    if s is None or (pair_id is not None and pair_id != s.pair_id):
        state = _ENDED.get(pair_id, "none") if pair_id else "none"
    else:
        state = s.state
    if for_collect:
        return {"burnt": "cancelled", "done": "used", "denied": "used"}.get(
            state, state if state in ("timed_out", "expired", "cancelled", "refused", "none")
            else "none")
    return {"done": "used", "denied": "used", "timed_out": "used", "refused": "used"}.get(
        state, state if state in ("expired", "burnt", "cancelled", "none") else "none")


def _mesh_refusal(where: str) -> tuple:
    return 403, {"ok": False, "reason": "not_mesh",
                 "error": PHONE_WORDS["this_pc" if where == "this_pc" else "not_mesh"]}


def _bad(reason: str = "bad_request") -> tuple:
    return 400, {"ok": False, "reason": reason, "error": PHONE_WORDS[reason]}


def claim(body, *, peer, local=None, own=None, gate: Optional[Callable] = None,
          tier_of: Optional[Callable] = None, spawn: Optional[Callable] = None) -> tuple:
    """POST /api/pair/claim - the phone's half, no key, mesh only."""
    where = mesh_peer(peer, local, own)
    if where != "mesh":
        return _mesh_refusal(where)
    if not isinstance(body, dict):
        return _bad()
    method = body.get("method")
    if method not in ("qr", "code"):
        return _bad()
    pair_id = body.get("pair_id") if method == "qr" else None
    if method == "qr" and not (isinstance(pair_id, str) and re.fullmatch(r"[0-9a-f]{16}", pair_id)):
        return _bad()
    gate = gate or _gate
    tier_of = tier_of or _tier
    spawn = spawn or _spawn
    with _LOCK:
        s = _tick()
        if s is None or (method == "qr" and pair_id != s.pair_id) or s.state in END_STATES:
            return 410, {"ok": False, "reason": "gone",
                         "state": _gone_state(s, pair_id if method == "qr" else None),
                         "error": PHONE_WORDS["gone"]}
        phone_nonce, name, proof = body.get("phone_nonce"), body.get("name"), body.get("proof")
        if not _nonce_ok(phone_nonce) or not isinstance(proof, str):
            return _bad()
        if not name_ok(name):
            return _bad("name")
        if s.state != "waiting_for_phone":
            # Already claimed: a second claim counts as a wrong try.
            return _wrong(s, peer)
        k = s.key(method)
        t = transcript(method, s.ref(method), phone_nonce, name)
        if not hmac.compare_digest(proof, claim_proof(k, t)):
            return _wrong(s, peer)
        s.method, s.phone_nonce, s.name = method, phone_nonce, name
        s.words = words_for(word_numbers(k, t, s.pc_nonce))
        s.state = "waiting_for_card"
        answer = {"state": "waiting_for_card", "pair_id": s.pair_id, "pc_nonce": s.pc_nonce,
                  "pc_proof": pc_proof(k, t, s.pc_nonce), "words": list(s.words),
                  "expires_in": s.expires_in()}
    try:
        spawn(lambda: _decide(s, gate, tier_of))
    except Exception:
        with _LOCK:
            if s.state == "waiting_for_card":
                s.state, s.method, s.phone_nonce, s.name, s.words = (
                    "waiting_for_phone", None, None, None, None)
        return 503, {"ok": False, "reason": "card", "error": PHONE_WORDS["card"]}
    _audit("devices.pair", {"state": "claimed"})
    return 202, answer


def _decide(s: Session, gate: Callable, tier_of: Callable) -> None:
    """Raise the pair_device card and wait for it (its own thread)."""
    text = card_text(s.name or "", s.words or [])
    try:
        if tier_of(ACTION) != "ask":
            raise LookupError("tier")
        v = gate(ACTION, {"text": text, "what": "connect a new device",
                          "device_name": s.name, "leaves_this_pc": False}, text)
        outcome, why = _verdict(v, ACTION, tier_of)
    except LookupError:
        outcome, why = "refused", "pair_device is not set to \"ask\""
    except Exception as exc:
        outcome, why = "refused", f"the approval gate failed ({type(exc).__name__})"
    with _LOCK:
        if _S["session"] is not s or s.state != "waiting_for_card":
            # Cancelled, replaced, burnt or expired while the card waited:
            # withdrawn - approving it makes no key.
            _audit("devices.pair", {"state": "withdrawn", "card": outcome})
            return
        if outcome == "approved":
            s.state = "approved"
            _audit("devices.pair", {"state": "approved"})
        else:
            _end(s, outcome, why)


def collect(body, *, peer, local=None, own=None) -> tuple:
    """POST /api/pair/collect - the key, once, after the card was approved."""
    where = mesh_peer(peer, local, own)
    if where != "mesh":
        return _mesh_refusal(where)
    if not isinstance(body, dict):
        return _bad()
    pair_id, proof = body.get("pair_id"), body.get("proof")
    if not isinstance(pair_id, str) or not isinstance(proof, str):
        return _bad()
    with _LOCK:
        s = _tick()
        if s is None or pair_id != s.pair_id:
            return 410, {"ok": False, "state": _gone_state(s, pair_id, for_collect=True),
                         "error": PHONE_WORDS["collect_gone"]}
        if s.state == "denied":
            return 403, {"ok": False, "state": "denied", "error": PHONE_WORDS["denied"]}
        if s.state in END_STATES:
            return 410, {"ok": False, "state": _gone_state(s, for_collect=True),
                         "error": PHONE_WORDS["collect_gone"]}
        if s.state == "waiting_for_phone":
            return _wrong(s, peer)
        if not hmac.compare_digest(proof, collect_proof(s.key(), s.pair_id, s.phone_nonce)):
            return _wrong(s, peer)
        if s.state == "waiting_for_card":
            return 202, {"state": "waiting_for_card", "expires_in": s.expires_in()}
        # approved: the key is made now, written as its hash, handed over once.
        try:
            device_id, token = _mint(s.name or "Phone")
        except Exception as exc:
            return 503, {"ok": False, "state": "approved",
                         "error": f"The device list could not be written ({type(exc).__name__}). "
                                  "Try again."}
        s.device_id = device_id
        _end(s, "done")
    _audit("devices.paired", {"id": device_id})
    _publish("devices", {})
    return 200, {"state": "approved", "device_id": device_id, "token": token}


def _mint(name: str) -> tuple:
    """A new device row and its key. Only the key's SHA-256 is written."""
    holder = {}

    def change(doc):
        taken = {r.get("id") for r in doc["devices"]}
        device_id = "d" + secrets.token_hex(4)
        while device_id in taken:
            device_id = "d" + secrets.token_hex(4)
        token = f"{KEY_PREFIX}{device_id}.{secrets.token_urlsafe(32)}"
        _hide(token)
        doc["devices"].append({"id": device_id, "name": name, "kind": "phone",
                               "token_sha256": _hash(token), "created": int(_wall()),
                               "last_seen": None, "removed": None, "approval_key": None})
        holder.update(id=device_id, token=token)

    _mutate(change)
    return holder["id"], holder["token"]


# ---------------------------------------------------------------------------
# The device list, Remove, Retire and Bring back (design 6.4)
# ---------------------------------------------------------------------------

_U_LOCK = threading.Lock()
_U: dict = {}              # {"id", "since"} while a Bring back card waits
_U_WITHDRAWN: set = set()
_U_LAST: dict = {}


def devices_view(*, you: str, here: bool, tier_of=None, armed=None) -> dict:
    """GET /api/devices. Never a key, never a hash."""
    doc, why = load()
    rows = [{"id": "pc", "name": "This PC", "kind": "pc", "removable": False,
             "this_device": you == "pc"}]
    with _SEEN_LOCK:
        seen = dict(_SEEN)
        other = dict(_OTHER)
    for r in doc["devices"]:
        if r.get("removed") or not r.get("token_sha256"):
            continue
        last = max([x for x in (r.get("last_seen"), seen.get(r["id"])) if isinstance(x, int)],
                   default=None)
        rows.append({"id": r["id"], "name": r.get("name", ""), "kind": r.get("kind", "phone"),
                     "created": r.get("created"), "last_seen": last,
                     "this_device": r["id"] == you, "removable": True,
                     "approval_key": False})
    sh = doc["shared"]
    last_other = max([x for x in (sh.get("last_other_seen"), other.get("at"))
                      if isinstance(x, int)], default=None)
    address = other.get("address") if other.get("at") == last_other and other.get("address") \
        else sh.get("last_other_address")
    with _U_LOCK:
        waiting = bool(_U)
    shared = {"retired": bool(sh["retired"]) or bool(why), "retired_at": sh.get("retired_at"),
              "last_other_seen": last_other, "last_other_address": address,
              "can_bring_back_here": bool(here)}
    if waiting:
        shared["waiting"] = True
    problem = why_not(tier_of, armed)
    return {"you": you, "devices": rows, "shared": shared,
            "pairing": {"available": problem is None, "why_not": problem}}


def remove(body, *, you: str) -> tuple:
    """POST /api/devices/remove {"id"} - immediate, no card, one device."""
    if not isinstance(body, dict) or set(body) != {"id"} or not isinstance(body["id"], str):
        return 400, {"ok": False, "reason": "bad_request",
                     "error": 'need {"id": "<one device id>"} and nothing else'}
    device_id = body["id"]
    if device_id == "pc":
        return 400, {"ok": False, "reason": "not_removable",
                     "error": "This PC cannot be removed."}
    if not _ID_RE.fullmatch(device_id):
        return 404, {"ok": False, "reason": "no_such_device", "error": "No such device."}
    holder = {}

    def change(doc):
        row = _live_row(doc, device_id)
        if row is None:
            return
        row["removed"] = int(_wall())
        row["token_sha256"] = ""
        holder["name"] = row.get("name", "")

    try:
        _mutate(change)
    except Broken:
        return 503, {"ok": False, "error": DEVICES_WORDS["registry_unreadable"]}
    except OSError as exc:
        return 503, {"ok": False, "error": f"The device list could not be written "
                                           f"({type(exc).__name__})."}
    if "name" not in holder:
        return 404, {"ok": False, "reason": "no_such_device", "error": "No such device."}
    with _SEEN_LOCK:
        _SEEN.pop(device_id, None)
    _audit("devices.removed", {"id": device_id})
    _publish("devices", {})
    return 200, {"ok": True, "id": device_id, "name": holder["name"],
                 "was_this_device": device_id == you}


def _u_finish(pid: str, outcome: str, why: str = "") -> None:
    with _U_LOCK:
        if _U.get("id") == pid:
            _U.clear()
        _U_WITHDRAWN.discard(pid)
        _U_LAST.clear()
        _U_LAST.update(outcome=outcome, why=why, at=_wall())
    _audit("devices.shared_card", {"outcome": outcome})


def _u_decide(pid: str, gate: Callable, tier_of: Callable) -> None:
    try:
        v = gate(UNRETIRE_ACTION, {"text": UNRETIRE_CARD_TEXT,
                                   "what": "let the old shared key work from other devices",
                                   "leaves_this_pc": False}, UNRETIRE_CARD_TEXT)
    except Exception as exc:
        return _u_finish(pid, "refused", f"the approval gate failed ({type(exc).__name__})")
    outcome, why = _verdict(v, UNRETIRE_ACTION, tier_of)
    if outcome != "approved":
        return _u_finish(pid, outcome, why)
    with _U_LOCK:
        withdrawn = pid in _U_WITHDRAWN
    if withdrawn:
        return _u_finish(pid, "withdrawn")

    def change(doc):
        doc["shared"]["retired"] = False
        doc["shared"]["retired_at"] = None

    try:
        _mutate(change)
    except Exception as exc:
        return _u_finish(pid, "failed", type(exc).__name__)
    _u_finish(pid, "approved")
    _audit("devices.shared", {"retired": False})
    _publish("devices", {})


def shared(body, *, you: str, here: bool, gate: Optional[Callable] = None,
           tier_of: Optional[Callable] = None, spawn: Optional[Callable] = None) -> tuple:
    """POST /api/devices/shared {"retired": true|false}."""
    if not isinstance(body, dict) or set(body) != {"retired"} \
            or not isinstance(body["retired"], bool):
        return 400, {"ok": False, "reason": "bad_request",
                     "error": 'need {"retired": true} or {"retired": false}'}
    gate = gate or _gate
    tier_of = tier_of or _tier
    spawn = spawn or _spawn
    if body["retired"]:
        if you == "shared" and not here:
            return 409, {"ok": False, "reason": "uses_it_yourself",
                         "error": DEVICES_WORDS["uses_it_yourself"]}
        with _U_LOCK:
            if _U:
                _U_WITHDRAWN.add(_U["id"])
                _U.clear()
        now = int(_wall())

        def change(doc):
            if not doc["shared"]["retired"]:
                doc["shared"]["retired"] = True
                doc["shared"]["retired_at"] = now

        try:
            _mutate(change)
        except Broken:
            return 503, {"ok": False, "error": DEVICES_WORDS["registry_unreadable"]}
        except OSError as exc:
            return 503, {"ok": False, "error": f"The device list could not be written "
                                               f"({type(exc).__name__})."}
        doc, _why = load()
        _audit("devices.shared", {"retired": True})
        _publish("devices", {})
        return 200, {"ok": True, "retired": True, "retired_at": doc["shared"].get("retired_at")}
    # Bring back - a loosening: PC only, a card with Windows Hello, never
    # under Lockdown.
    if not here:
        return 403, {"ok": False, "pc_only": True, "error": PC_ONLY}
    if _lockdown_on():
        return 409, {"ok": False, "error": _lockdown_words(), "lockdown": True}
    doc, why = load()
    if why:
        return 503, {"ok": False, "error": DEVICES_WORDS["registry_unreadable"]}
    if not doc["shared"]["retired"]:
        return 200, {"ok": True, "retired": False, "waiting": False}
    tier = tier_of(UNRETIRE_ACTION)
    if tier != "ask":
        return 503, {"ok": False, "error": (
            f"{UNRETIRE_ACTION} is tier {tier!r} in jarvis-framework.toml; bringing the old "
            f"shared key back needs a person to say yes, so it must be 'ask'")}
    with _U_LOCK:
        if _U:
            return 202, {"ok": True, "waiting": True,
                         "message": DEVICES_WORDS["unretire_waiting"]}
        pid = secrets.token_hex(8)
        _U.update(id=pid, since=_wall())
    try:
        spawn(lambda: _u_decide(pid, gate, tier_of))
    except Exception:
        with _U_LOCK:
            _U.clear()
        return 503, {"ok": False, "error": "could not raise the approval card"}
    return 202, {"ok": True, "waiting": True, "message": DEVICES_WORDS["unretire_waiting"]}


# ---------------------------------------------------------------------------
# The routes - wrapped round the handler, like jarvis_owner_check.install()
# ---------------------------------------------------------------------------

GET_ROUTES = ("/api/pair/session", "/api/devices")
POST_ROUTES = ("/api/pair/start", "/api/pair/cancel", "/api/pair/claim", "/api/pair/collect",
               "/api/devices/remove", "/api/devices/shared")
#: The only routes in Jarvis that take no key: the phone has none yet.
KEYLESS = ("/api/pair/claim", "/api/pair/collect")

_ARMED = False


def armed() -> bool:
    """True once install() has wrapped the server. /api/version reports it
    as capabilities.pairing = {"version": 1}."""
    return _ARMED


def capability():
    """capabilities.pairing for /api/version: {"version": 1}, or False."""
    return {"version": 1} if _ARMED else False


def _own_port(handler) -> Optional[int]:
    try:
        return int(handler.connection.getsockname()[1])
    except Exception:
        pass
    main = sys.modules.get("__main__")
    try:
        return int(getattr(main, "HUD_PORT"))
    except Exception:
        return None


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET` and `do_POST` for the pairing and device
    routes. Every other request goes straight to the original. `token_ok`
    is wrapped too (idempotent), so a device key is checked here even if the
    caller passed the original. Returns the banner line."""
    global _ARMED
    token_ok = wrap_token_ok(token_ok)
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(post0, "_jarvis_devices", False):
        _ARMED = True
        return "  devices    a key per device, pairing by QR code (already on)"

    def _allowed(self, *, keyless: bool) -> bool:
        try:
            if not origin_ok(self):
                self._send(403, {"error": "cross-origin request refused"})
                return False
            if not keyless and not token_ok(self):
                self._send(401, {"error": "bad or missing X-Jarvis-Token"})
                return False
        except Exception:
            self._send(401, {"error": "bad or missing X-Jarvis-Token"})
            return False
        return True

    def _body(self):
        try:
            body = json.loads(read_body(self) or b"{}")
        except Exception:
            return None
        return body

    def do_GET(self):
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route not in GET_ROUTES:
            return get0(self)
        if not _allowed(self, keyless=False):
            return None
        peer, local = _peer_local(self)
        here = from_this_pc(peer, local)
        try:
            if route == "/api/pair/session":
                code, out = session_view(here=here)
            else:
                code, out = 200, devices_view(you=_who(self), here=here)
        except Exception as exc:
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    def do_POST(self):
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route not in POST_ROUTES:
            return post0(self)
        if not _allowed(self, keyless=route in KEYLESS):
            return None
        peer, local = _peer_local(self)
        body = _body(self)
        try:
            if route == "/api/pair/claim":
                code, out = claim(body, peer=peer, local=local)
            elif route == "/api/pair/collect":
                code, out = collect(body, peer=peer, local=local)
            else:
                here = from_this_pc(peer, local)
                you = _who(self)
                if route == "/api/pair/start":
                    code, out = start(body, here=here, default_port=_own_port(self))
                elif route == "/api/pair/cancel":
                    code, out = cancel(here=here)
                elif route == "/api/devices/remove":
                    code, out = remove(body, you=you)
                    if out.get("was_this_device"):
                        # Its own answer still goes out; the next write does not.
                        self._jarvis_guard_device = None
                else:
                    code, out = shared(body, you=you, here=here)
        except Exception as exc:
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    do_GET._jarvis_devices = True
    do_POST._jarvis_devices = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    _ARMED = True
    doc, why = load()
    if why:
        return "  devices    the device list cannot be read - only this PC can reach Jarvis"
    n = sum(1 for r in doc["devices"] if not r.get("removed") and r.get("token_sha256"))
    retired = " ; old shared key retired (this PC only)" if doc["shared"]["retired"] else ""
    return f"  devices    {n} paired device(s), pairing by QR code on{retired}"


if __name__ == "__main__":
    if "--start-fresh" in sys.argv:
        print("  " + start_fresh())
        sys.exit(0)
    doc, why = load()
    if why:
        print(f"  devices    {DEVICES_WORDS['registry_unreadable']}")
        sys.exit(1)
    live = [r for r in doc["devices"] if not r.get("removed") and r.get("token_sha256")]
    print(f"  devices    {len(live)} paired")
    for r in live:
        print(f"             {r['id']}  {r.get('name', '')}")
    print(f"  shared key {'retired (this PC only)' if doc['shared']['retired'] else 'works'}")
