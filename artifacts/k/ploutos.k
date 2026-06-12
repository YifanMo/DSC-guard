requires "domains.md"

module DSC-GUARD-PLOUTOS-SYNTAX
  imports INT
  imports STRING
  imports LIST
  imports MAP

  syntax Event ::= oracleFeedSet(String, String, String, String)
                 | oracleAnswer(String, String, Int, Int, Int, Int, String)
                 | oracleFormulaSet(String, String, String, String)
                 | supply(String, String, String, String)
                 | borrow(String, String, String, String, String)
                 | liquidate(String, String, String, String, String)
                 | pauseMarket(String, String)
                 | rawLog(String)
  syntax Events ::= List
endmodule

module DSC-GUARD-PLOUTOS
  imports DSC-GUARD-PLOUTOS-SYNTAX
  imports INT
  imports STRING
  imports LIST
  imports MAP

  configuration
    <dscGuard>
      <k> $PGM:Events </k>
      <block> 0 </block>
      <tx> "" </tx>
      <log> .List </log>
      <oracleMap> .Map </oracleMap>
      <oracleAnswer> .Map </oracleAnswer>
      <marketState> .Map </marketState>
      <balances> .Map </balances>
      <positions> .Map </positions>
      <alerts> .List </alerts>
    </dscGuard>

  // Generic log-driven transition rules.
  rule <k> ListItem(oracleFeedSet(ASSET, EXPECTED, ACTUAL, TX)) => . ... </k>
       <tx> _ => TX </tx>
       <oracleMap> OM => OM [ ASSET <- ACTUAL ] </oracleMap>
       <alerts> A => A ListItem("feed-mismatch:" +String TX) </alerts>
    requires EXPECTED =/=String ACTUAL

  rule <k> ListItem(oracleAnswer(ASSET, FEED, ANSWER, UPDATEDAT, ROUNDID, ANSWEREDINROUND, TX)) => . ... </k>
       <tx> _ => TX </tx>
       <oracleAnswer> OA => OA [ ASSET <- FEED +String ":" +String Int2String(ANSWER) +String ":" +String Int2String(UPDATEDAT) ] </oracleAnswer>
       <log> L => L ListItem(TX) </log>

  rule <k> ListItem(oracleFormulaSet(ASSET, EXPECTED, ACTUAL, TX)) => . ... </k>
       <tx> _ => TX </tx>
       <alerts> A => A ListItem("formula-mismatch:" +String TX) </alerts>
    requires EXPECTED =/=String ACTUAL

  rule <k> ListItem(supply(ACCOUNT, ASSET, AMOUNT, TX)) => . ... </k>
       <tx> _ => TX </tx>
       <positions> P => P [ ACCOUNT +String ":supply:" +String ASSET <- AMOUNT ] </positions>

  rule <k> ListItem(borrow(ACCOUNT, COLLATERAL, BORROWASSET, AMOUNT, TX)) => . ... </k>
       <tx> _ => TX </tx>
       <positions> P => P [ ACCOUNT +String ":borrow:" +String BORROWASSET <- AMOUNT ] </positions>

  rule <k> ListItem(liquidate(LIQUIDATOR, BORROWER, COLLATERAL, AMOUNT, TX)) => . ... </k>
       <tx> _ => TX </tx>
       <positions> P => P [ LIQUIDATOR +String ":liquidate:" +String COLLATERAL <- AMOUNT ] </positions>

  rule <k> ListItem(pauseMarket(ASSET, TX)) => . ... </k>
       <tx> _ => TX </tx>
       <marketState> M => M [ ASSET <- "paused" ] </marketState>

  // Case constraints embedded for auditability.
  // constraint USDC_FEED_MUST_BE_USDC_USD: type=feed_mismatch severity=critical
  // constraint BORROW_MUST_BE_COLLATERALIZED: type=borrow_collateralization severity=critical

  // Slither-mined event semantics.
  // AaveOracle-constructor-BaseCurrencySet: oracle-read
  //   cfg: _setFallbackOracle(fallbackOracle)
  //   cfg: ADDRESSES_PROVIDER = provider
  //   cfg: BASE_CURRENCY = baseCurrency
  //   cfg: BASE_CURRENCY_UNIT = baseCurrencyUnit
  // AaveOracle-setAssetsSources-AssetSourceUpdated: oracle-setter
  //   cfg: assetsSources[assets[i]] = AggregatorInterface(sources[i])
  // AaveOracle-setFallbackOracle-FallbackOracleUpdated: oracle-read, oracle-setter
  //   cfg: _fallbackOracle = IPriceOracleGetter(fallbackOracle)
  //   cfg: FallbackOracleUpdated(fallbackOracle)
endmodule
