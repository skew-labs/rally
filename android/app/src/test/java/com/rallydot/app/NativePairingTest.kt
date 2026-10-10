package com.rallydot.app
import org.junit.Test
import org.junit.Assert.*
import org.json.JSONObject
class NativePairingTest {
    private val pending=NativePairing("a".repeat(32),"b".repeat(43),"0123",1600)
    @Test fun proofRestoresWithoutPuttingVerifierInReturnLink() {
        val restored=NativePairing.read(JSONObject(pending.json().toString()),1100)
        assertEquals(pending,restored);assertFalse(restored.url.contains(restored.verifier))
        assertEquals(pending.verifier,restored.poll().string("verifier"))
        assertEquals(pending,NativePairing.fromStart(JSONObject().put("id",pending.id).put("code",pending.code).put("url",pending.url).put("expiresIn",600),pending.verifier,1000))
    }
    @Test fun expiredOrForeignRequestsCannotRestore() {
        for(data in listOf(pending.json().put("expires",1000),pending.json().put("verifier","bad"),pending.json().put("id","bad"))) {
            try { NativePairing.read(data,1000);fail("Must reject") } catch(_:IllegalArgumentException) { }
        }
        try { NativePairing.fromStart(JSONObject().put("id",pending.id).put("code",pending.code).put("url","https://attacker.example").put("expiresIn",600),pending.verifier,1000);fail("Must reject") } catch(_:IllegalArgumentException) { }
    }
    @Test fun returnLinksOnlyWakeFirstPartyAccountConnection() {
        assertTrue(pairingReturn("https://rallydot.com/native-return?nativeRequest="+pending.id))
        assertTrue(pairingReturn("rallyconnect://account?nativeRequest="+pending.id))
        for(url in listOf("https://attacker.example/native-return","https://rallydot.com.attacker.example/native-return","https://rallydot.com:443/native-return","rallyconnect://wallet","https://user@rallydot.com/native-return"))assertFalse(pairingReturn(url))
    }
}
