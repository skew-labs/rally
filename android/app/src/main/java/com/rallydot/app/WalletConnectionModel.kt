package com.rallydot.app

import org.json.JSONObject

data class ExternalWalletBrand(val id: String,val name: String,val image: String,val packageName: String,val scheme: String)
val externalWalletBrands=listOf(
    ExternalWalletBrand("metamask","MetaMask","agent-metamask.svg","io.metamask","metamask"),
    ExternalWalletBrand("rainbow","Rainbow","wallet-rainbow.svg","me.rainbow","rainbow"),
    ExternalWalletBrand("trust","Trust Wallet","wallet-trust.svg","com.wallet.crypto.trustapp","trust")
)
fun caipWallet(accounts: List<String>,expected: String?=null,chain: String?=null): Pair<String,String> {
    val parsed=accounts.mapNotNull {
        val fields=it.split(':')
        if(fields.size==3 && fields[0]=="eip155" && fields[1] in listOf("143","1") && Regex("0x[0-9a-fA-F]{40}").matches(fields[2]) && fields[2]!= "0x"+"0".repeat(40))
            "eip155:${fields[1]}" to fields[2].lowercase() else null
    }.filter { (c,a)->(expected==null || a.equals(expected,true)) && (chain==null || c==chain) }
    return parsed.firstOrNull { it.first=="eip155:143" } ?: parsed.firstOrNull() ?: error("Choose a supported wallet account")
}
fun checkedLoginProof(proof: JSONObject,address: String,link: Boolean,now: Long=System.currentTimeMillis()/1000): String {
    val message=proof.string("message")
    require(proof.string("id").isNotBlank() && proof.optLong("expires")>now && proof.optInt("chainId")==143 && proof.string("purpose")== (if(link)"link_wallet" else "sign_in")) { "Login expired. Connect again." }
    val lines=message.lines()
    require(lines.size==11 && lines[0]=="rallydot.com wants you to sign in with your Ethereum account:" && lines[1].equals(address,true) &&
        lines[2].isEmpty() && lines[4].isEmpty() && lines[5]=="URI: $ORIGIN" && lines[6]=="Version: 1" && lines[7]=="Chain ID: 143" &&
        lines[8].startsWith("Nonce: ") && Regex("[a-f0-9]{32}").matches(lines[8].removePrefix("Nonce: ")) &&
        lines[3]==(if(link)"Link this wallet to your Rally account." else "Sign in to Rally.")+" No transaction or spending permission.") { "Wallet request does not belong to Rally" }
    val issued=runCatching { java.time.Instant.parse(lines[9].removePrefix("Issued At: ")).epochSecond }.getOrNull()
    val expiry=runCatching { java.time.Instant.parse(lines[10].removePrefix("Expiration Time: ")).epochSecond }.getOrNull()
    require(lines[9].startsWith("Issued At: ") && lines[10].startsWith("Expiration Time: ") && issued!=null && issued<=now+30 && expiry==proof.optLong("expires") && expiry>issued) { "Login expired. Connect again." }
    return message
}
