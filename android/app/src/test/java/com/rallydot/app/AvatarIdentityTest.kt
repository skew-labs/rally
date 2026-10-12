package com.rallydot.app
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class AvatarIdentityTest {
 @Test fun sharedWebIdentityVectorsMatchIncludingSurrogatePairs() {
  for((id,namespace,expected) in listOf(Triple("guest","profile",5),Triple("alice","profile",5),Triple("studio","community",3),Triple("a🐈","profile",3),Triple("2a785c16f45743309f82f6c80a45ec35","profile",0)))assertEquals(expected,avatarIndex(id,namespace))
 }
 @Test fun editorialFacesAreDistinctAndStableAfterRename() {
  val ids=listOf("rally","ce835f7aadde4129bfe8d993385c21d2","1a4c47df1581408e913ca68056d07fe7","c0d47e94549f4e5c93c9e0eacce45c25")
  assertEquals(4,ids.map { avatarDrawable(it) }.toSet().size)
  for(id in ids) {
   val before=Person(id,"Before","before",null,false);val after=before.copy(name="After",handle="after")
   assertEquals(avatarDrawable(before.avatarIdentity),avatarDrawable(after.avatarIdentity))
  }
 }
 @Test fun algorithmOwnerFallbackMatchesTheProfileIdentity() {
  val feed=JSONObject().put("owner","rally").put("creator",JSONObject().put("name","Rally").put("handle","rally"))
  assertEquals("rally",discoveryCreator(feed,emptyList()).avatarIdentity)
  assertEquals(avatarDrawable("rally"),avatarDrawable(discoveryCreator(feed,emptyList()).avatarIdentity))
 }
}
