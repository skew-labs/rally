package com.rallydot.app
import org.junit.Assert.*
import org.junit.Test
class TokenMarketDisplayTest {
 @Test fun capAndVolumePreserveUsefulPrecision(){assertEquals("$9.92M",marketCompactUSD(9920000.0));assertEquals("$76.7K",marketCompactUSD(76700.0));assertEquals("$0",marketCompactUSD(0.0));assertEquals("—",marketCompactUSD(null))}
 @Test fun datesNeverSubstituteCurrentTime(){assertEquals("20m",marketTokenAge(1000,2200));assertNull(marketTokenAge(0,2200));assertNull(marketTokenAge(2300,2200));assertEquals("now",marketTokenAge(2190,2200))}
}
