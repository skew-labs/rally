package com.rallydot.app

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class ArtworkSourcesTest {
    @Test fun blankThumbnailKeepsTheOriginalAndExactRegistryFallback() {
        val raw=JSONObject().put("id","0xabc").put("symbol","BTC").put("logoThumbURI","").put("logoURI","https://images.example/token.png").put("logoCandidates",JSONArray().put("/assets/exact.png").put("https://images.example/token.png"))
        val a=Asset.parse(raw)
        assertEquals("https://images.example/token.png",a.image)
        assertEquals(listOf("https://images.example/token.png",ORIGIN+"/assets/exact.png"),a.artworkSources)
    }
    @Test fun unsafeCandidatesAreIgnoredAndRecoveryIsBounded() {
        val a=Asset.parse(JSONObject().put("id","0xother").put("symbol","BTC").put("logoCandidates",JSONArray().put("http://localhost/image").put("javascript:alert(1)").put("/assets/a.png").put("/assets/b.png")))
        assertEquals(listOf(ORIGIN+"/assets/a.png",ORIGIN+"/assets/b.png"),a.artworkSources)
        assertNull(a.image)
    }
}
