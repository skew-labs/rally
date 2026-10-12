package com.rallydot.app

// Shared with avatar-identity.js. Never seed a face from a mutable display name.
fun avatarIndex(identity: String, namespace: String="profile"): Int {
    if(namespace=="profile")when(identity) {
        "rally"->return 0
        "ce835f7aadde4129bfe8d993385c21d2"->return 1
        "1a4c47df1581408e913ca68056d07fe7"->return 2
        "c0d47e94549f4e5c93c9e0eacce45c25"->return 4
    }
    return ((namespace+":"+identity.ifBlank { "guest" }).hashCode() and Int.MAX_VALUE)%6
}
fun avatarDrawable(identity: String, namespace: String="profile"): Int=when(avatarIndex(identity,namespace)) {
    1->R.drawable.rally_character_mint
    2->R.drawable.rally_character_coral
    3->R.drawable.rally_character_blue
    4->R.drawable.rally_character_gold
    5->R.drawable.rally_character_rose
    else->R.drawable.rally_character
}
val Person.avatarIdentity: String get()=id.ifBlank { handle }
