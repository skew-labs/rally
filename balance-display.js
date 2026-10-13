// Zero is a neutral display placeholder, never stored as a measured return.
export function dailyBalance(valuation, format) {
 const raw=valuation?.change24hPercent, value=raw==null?null:Number(raw);
 const known=value!==null&&Number.isFinite(value);
 return {known,text:known?format(value):'0.00%',tone:known?(value>=0?'positive':'negative'):'',
  description:known?'24h price change of current holdings':'24h price history pending; zero is a display placeholder'};
}
