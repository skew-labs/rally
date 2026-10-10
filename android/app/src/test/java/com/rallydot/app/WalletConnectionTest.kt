package com.rallydot.app
import org.junit.Assert.*
import org.junit.Test
import org.json.JSONObject
class WalletConnectionTest {
    private val address="0x"+"1".repeat(40)
    private fun proof(link: Boolean=false)=JSONObject().put("id","fixture-proof").put("expires",2000).put("chainId",143).put("purpose",if(link)"link_wallet" else "sign_in").put("message",
        "rallydot.com wants you to sign in with your Ethereum account:\n$address\n\n"+(if(link)"Link this wallet to your Rally account." else "Sign in to Rally.")+" No transaction or spending permission.\n\nURI: $ORIGIN\nVersion: 1\nChain ID: 143\nNonce: "+"a".repeat(32)+"\nIssued At: 1970-01-01T00:15:00Z\nExpiration Time: 1970-01-01T00:33:20Z")
    private fun rejected(action: ()->Unit) { try { action();fail("Must reject") } catch(_:IllegalArgumentException){} catch(_:IllegalStateException){} }
    @Test fun loginProofCannotCrossOriginChainAddressPurposeOrExpiry() {
        val good=proof();assertEquals(good.string("message"),checkedLoginProof(good,address,false,1000))
        rejected { checkedLoginProof(good,address,false,2000) }
        rejected { checkedLoginProof(good,"0x"+"2".repeat(40),false,1000) }
        rejected { checkedLoginProof(good,address,true,1000) }
        rejected { checkedLoginProof(proof().put("chainId",1),address,false,1000) }
        rejected { checkedLoginProof(proof().put("message",good.string("message")+"\nApprove spending"),address,false,1000) }
        rejected { checkedLoginProof(proof().put("expires",2100),address,false,1000) }
        for(pair in listOf(ORIGIN to "https://attacker.example","Chain ID: 143" to "Chain ID: 1","Nonce: "+"a".repeat(32) to "Nonce: missing","No transaction or spending permission." to "Approve token spending.")) {
            rejected { checkedLoginProof(proof().put("message",good.string("message").replace(pair.first,pair.second)),address,false,1000) }
        }
        assertEquals(proof(true).string("message"),checkedLoginProof(proof(true),address,true,1000))
    }
    @Test fun walletNamespacesMustMatchSelectedAddressAndTransactionChain() {
        assertEquals("eip155:143",caipWallet(listOf("eip155:1:$address","eip155:143:$address")).first)
        assertEquals(address,caipWallet(listOf("eip155:1:$address"),address.uppercase()).second)
        rejected { caipWallet(listOf("eip155:1:$address"),address,"eip155:143") }
        rejected { caipWallet(listOf("eip155:143:$address"),"0x"+"2".repeat(40)) }
        for(value in listOf("eip155:143:0x"+"0".repeat(40),"solana:1:$address","eip155:999:$address","eip155:143:bad"))rejected { caipWallet(listOf(value)) }
    }
}
