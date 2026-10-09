package com.rallydot.app
import org.json.JSONObject
import org.junit.Test
import org.junit.Assert.*
class WalletTransferTest {
 private val recipient="0x"+"2".repeat(40)
 private val token="0x"+"3".repeat(40)
 private fun holding(asset: String=token)=JSONObject().put("asset",asset).put("token",JSONObject().put("address",token).put("decimals",6))
 private fun plan(native: Boolean=false): JSONObject {
  val raw=if(native)"10000000000000000" else "10000"
  return JSONObject().put("approval",JSONObject.NULL).put("summary",JSONObject().put("action","send").put("recipient",recipient).put("token",if(native)"MON" else token).put("amountRaw",raw)).put("transaction",JSONObject().put("to",if(native)recipient else token).put("value",if(native)"0x"+raw.toBigInteger().toString(16) else "0x0").put("data",if(native)"0x" else "0xa9059cbb"+recipient.removePrefix("0x").padStart(64,'0')+10000.toString(16).padStart(64,'0')))
 }
 @Test fun exactERC20SendHasNoAllowance() { assertNotNull(checkedNativeTransfer(plan(),holding(),recipient,"0.01")) }
 @Test fun exactNativeSendCarriesValue() { assertNotNull(checkedNativeTransfer(plan(true),holding("MON"),recipient,"0.01")) }
 @Test fun alteredRecipientNeverReachesSDK() { val p=plan();p.getJSONObject("transaction").put("to",recipient);try { checkedNativeTransfer(p,holding(),recipient,"0.01");fail("Changed token accepted") } catch(_:IllegalArgumentException) {} }
 @Test fun alteredAmountNeverReachesSDK() { try { checkedNativeTransfer(plan(),holding(),recipient,"1");fail("Changed amount accepted") } catch(_:IllegalArgumentException) {} }
 @Test fun hiddenTokenApprovalIsRejected() { val p=plan().put("approval",JSONObject());try { checkedNativeTransfer(p,holding(),recipient,"0.01");fail("Approval accepted") } catch(_:IllegalArgumentException) {} }
 @Test fun prepareCannotChangeVerifiedTransfer() { val p=plan();p.getJSONObject("summary").put("action","send");val prep=JSONObject().put("transaction",JSONObject(p.getJSONObject("transaction").toString()).put("to",recipient));try { checkedPreparedTransfer(p,prep);fail("Prepared transfer changed") } catch(_:IllegalArgumentException) {} }
 @Test fun preparationMayAddGasWithoutChangingSend() { val p=plan();p.getJSONObject("summary").put("action","send");checkedPreparedTransfer(p,JSONObject().put("transaction",JSONObject(p.getJSONObject("transaction").toString()).put("gas","0x10000"))) }
 @Test fun successfulInclusionDoesNotFinishUnverifiedTransfer() { val e=JSONObject().put("state","finalized").put("outcome",JSONObject().put("businessState","transfer_unverified"));assertFalse(orderOutcome(e).completed);e.getJSONObject("outcome").put("businessState","sent");assertTrue(orderOutcome(e).completed);assertEquals("Transfer complete",orderOutcome(e).label) }
}
