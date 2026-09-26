package com.jarvis.client.net

/**
 * Where an approval card can be answered - said the same way everywhere the
 * phone raises one.
 *
 * The phone used to send the owner to three different places for the same
 * card: "on your desktop or in Inbox" (the wake word - but Inbox holds no
 * cards, it only links to them), "on your PC or phone" (the second card, the
 * big model, voice training), "on the desktop" only (note filing), and "a
 * card on Home" (a model switch or install). The cards are on Home
 * (`HomeScreen`'s approval list) and on the PC, so every one of those now
 * uses this one sentence. It follows a sentence that has already said a card
 * is waiting, so "it" is always that card.
 */
object Approvals {
    const val WHERE = "Approve it on your PC or on this phone's Home screen."
}
