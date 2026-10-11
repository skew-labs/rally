package com.rallydot.app

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class AlgorithmLibraryTest {
    private fun catalog(): JSONObject {
        val entries=JSONArray()
        for(i in 1..100)entries.put(JSONObject().put("id","rally-ref-%03d".format(i)).put("status","reference").put("icon","/assets/algorithm-ref-%03d-1234567890abcdef.png".format(i)).put("sourceURL","https://www.aqr.com/"))
        return JSONObject().put("version",1).put("items",entries)
    }
    @Test fun publicReferencesHaveNoExecutionTerms(){assertEquals(100,validateAlgorithmReferences(catalog()).size)}
    @Test fun rejectPurchasableReference(){val data=catalog();data.getJSONArray("items").getJSONObject(0).put("price",10);assertThrows(IllegalArgumentException::class.java){validateAlgorithmReferences(data)}}
    @Test fun rejectExternalArtwork(){val data=catalog();data.getJSONArray("items").getJSONObject(0).put("icon","https://tracker.example/icon.png");assertThrows(IllegalArgumentException::class.java){validateAlgorithmReferences(data)}}
    @Test fun rejectUnsafeSource(){val data=catalog();data.getJSONArray("items").getJSONObject(0).put("sourceURL","javascript:alert(1)");assertThrows(IllegalArgumentException::class.java){validateAlgorithmReferences(data)}}
    @Test fun rejectDuplicateReferences(){val data=catalog();data.getJSONArray("items").getJSONObject(1).put("id","rally-ref-001");assertThrows(IllegalArgumentException::class.java){validateAlgorithmReferences(data)}}
}
