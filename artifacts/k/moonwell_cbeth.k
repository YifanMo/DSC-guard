requires "domains.md"

module DSC-GUARD-MOONWELL-CBETH-SYNTAX
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

module DSC-GUARD-MOONWELL-CBETH
  imports DSC-GUARD-MOONWELL-CBETH-SYNTAX
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
  // constraint CBETH_USD_MUST_MULTIPLY_ETH_USD: type=formula_mismatch severity=critical

  // Slither-mined event semantics.
  // ComptrollerErrorReporter-fail-Failure: 
  // ComptrollerErrorReporter-failOpaque-Failure: 
  // TokenErrorReporter-fail-Failure: 
  // TokenErrorReporter-failOpaque-Failure: 
  // ComptrollerErrorReporter-fail-Failure: 
  // ComptrollerErrorReporter-failOpaque-Failure: 
  // TokenErrorReporter-fail-Failure: 
  // TokenErrorReporter-failOpaque-Failure: 
  // MToken-transferTokens-Transfer: transfer
  //   cfg: startingAllowance = transferAllowances[src][spender]
  //   cfg: (mathErr,srcTokensNew) = subUInt(accountTokens[src],tokens)
  //   cfg: (mathErr,dstTokensNew) = addUInt(accountTokens[dst],tokens)
  //   cfg: accountTokens[src] = srcTokensNew
  //   cfg: accountTokens[dst] = dstTokensNew
  // MToken-approve-Approval: transfer
  //   cfg: transferAllowances[src][spender] = amount
  // MToken-accrueInterest-AccrueInterest: borrow
  //   cfg: accrualBlockTimestampPrior = accrualBlockTimestamp
  //   cfg: accrualBlockTimestampPrior == currentBlockTimestamp
  //   cfg: borrowsPrior = totalBorrows
  //   cfg: reservesPrior = totalReserves
  //   cfg: borrowIndexPrior = borrowIndex
  // MToken-mintFresh-Mint: mint, supply, transfer
  //   cfg: (vars.mathErr,vars.totalSupplyNew) = addUInt(totalSupply,vars.mintTokens)
  //   cfg: (vars.mathErr,vars.accountTokensNew) = addUInt(accountTokens[minter],vars.mintTokens)
  //   cfg: totalSupply = vars.totalSupplyNew
  //   cfg: accountTokens[minter] = vars.accountTokensNew
  // MToken-mintFresh-Transfer: mint, supply, transfer
  //   cfg: (vars.mathErr,vars.totalSupplyNew) = addUInt(totalSupply,vars.mintTokens)
  //   cfg: (vars.mathErr,vars.accountTokensNew) = addUInt(accountTokens[minter],vars.mintTokens)
  //   cfg: totalSupply = vars.totalSupplyNew
  //   cfg: accountTokens[minter] = vars.accountTokensNew
  // MToken-redeemFresh-Transfer: redeem, supply, transfer
  //   cfg: vars.redeemTokens = accountTokens[redeemer]
  //   cfg: (vars.mathErr,vars.totalSupplyNew) = subUInt(totalSupply,vars.redeemTokens)
  //   cfg: (vars.mathErr,vars.accountTokensNew) = subUInt(accountTokens[redeemer],vars.redeemTokens)
  //   cfg: totalSupply = vars.totalSupplyNew
  //   cfg: accountTokens[redeemer] = vars.accountTokensNew
  // MToken-redeemFresh-Redeem: redeem, supply, transfer
  //   cfg: vars.redeemTokens = accountTokens[redeemer]
  //   cfg: (vars.mathErr,vars.totalSupplyNew) = subUInt(totalSupply,vars.redeemTokens)
  //   cfg: (vars.mathErr,vars.accountTokensNew) = subUInt(accountTokens[redeemer],vars.redeemTokens)
  //   cfg: totalSupply = vars.totalSupplyNew
  //   cfg: accountTokens[redeemer] = vars.accountTokensNew
  // MToken-borrowFresh-Borrow: borrow, transfer
  //   cfg: (vars.mathErr,vars.accountBorrows) = borrowBalanceStoredInternal(borrower)
  //   cfg: (vars.mathErr,vars.accountBorrowsNew) = addUInt(vars.accountBorrows,borrowAmount)
  //   cfg: (vars.mathErr,vars.totalBorrowsNew) = addUInt(totalBorrows,borrowAmount)
  //   cfg: accountBorrows[borrower].principal = vars.accountBorrowsNew
  //   cfg: accountBorrows[borrower].interestIndex = borrowIndex
  // MToken-repayBorrowFresh-RepayBorrow: borrow, transfer
  //   cfg: vars.borrowerIndex = accountBorrows[borrower].interestIndex
  //   cfg: (vars.mathErr,vars.accountBorrows) = borrowBalanceStoredInternal(borrower)
  //   cfg: vars.repayAmount = vars.accountBorrows
  //   cfg: (vars.mathErr,vars.accountBorrowsNew) = subUInt(vars.accountBorrows,vars.actualRepayAmount)
  //   cfg: (vars.mathErr,vars.totalBorrowsNew) = subUInt(totalBorrows,vars.actualRepayAmount)
  // MToken-liquidateBorrowFresh-LiquidateBorrow: borrow, liquidate
  // MToken-seizeInternal-Transfer: borrow, liquidate, supply, transfer
  //   cfg: (vars.mathErr,vars.borrowerTokensNew) = subUInt(accountTokens[borrower],seizeTokens)
  //   cfg: vars.totalReservesNew = add_(totalReserves,vars.protocolSeizeAmount)
  //   cfg: vars.totalSupplyNew = sub_(totalSupply,vars.protocolSeizeTokens)
  //   cfg: (vars.mathErr,vars.liquidatorTokensNew) = addUInt(accountTokens[liquidator],vars.liquidatorSeizeTokens)
  //   cfg: totalReserves = vars.totalReservesNew
  // MToken-seizeInternal-Transfer: borrow, liquidate, supply, transfer
  //   cfg: (vars.mathErr,vars.borrowerTokensNew) = subUInt(accountTokens[borrower],seizeTokens)
  //   cfg: vars.totalReservesNew = add_(totalReserves,vars.protocolSeizeAmount)
  //   cfg: vars.totalSupplyNew = sub_(totalSupply,vars.protocolSeizeTokens)
  //   cfg: (vars.mathErr,vars.liquidatorTokensNew) = addUInt(accountTokens[liquidator],vars.liquidatorSeizeTokens)
  //   cfg: totalReserves = vars.totalReservesNew
  // MToken-seizeInternal-ReservesAdded: borrow, liquidate, supply, transfer
  //   cfg: (vars.mathErr,vars.borrowerTokensNew) = subUInt(accountTokens[borrower],seizeTokens)
  //   cfg: vars.totalReservesNew = add_(totalReserves,vars.protocolSeizeAmount)
  //   cfg: vars.totalSupplyNew = sub_(totalSupply,vars.protocolSeizeTokens)
  //   cfg: (vars.mathErr,vars.liquidatorTokensNew) = addUInt(accountTokens[liquidator],vars.liquidatorSeizeTokens)
  //   cfg: totalReserves = vars.totalReservesNew
  // MToken-setPendingAdmin-NewPendingAdmin: 
  //   cfg: oldPendingAdmin = pendingAdmin
  //   cfg: pendingAdmin = newPendingAdmin
  //   cfg: NewPendingAdmin(oldPendingAdmin,newPendingAdmin)
  // MToken-acceptAdmin-NewAdmin: 
  //   cfg: msg.sender != pendingAdmin || msg.sender == address(0)
  //   cfg: fail(Error.UNAUTHORIZED,FailureInfo.ACCEPT_ADMIN_PENDING_ADMIN_CHECK)
  //   cfg: oldAdmin = admin
  //   cfg: oldPendingAdmin = pendingAdmin
  //   cfg: admin = pendingAdmin
  // MToken-acceptAdmin-NewPendingAdmin: 
  //   cfg: msg.sender != pendingAdmin || msg.sender == address(0)
  //   cfg: fail(Error.UNAUTHORIZED,FailureInfo.ACCEPT_ADMIN_PENDING_ADMIN_CHECK)
  //   cfg: oldAdmin = admin
  //   cfg: oldPendingAdmin = pendingAdmin
  //   cfg: admin = pendingAdmin
  // MToken-setComptroller-NewComptroller: 
  //   cfg: fail(Error.UNAUTHORIZED,FailureInfo.SET_COMPTROLLER_OWNER_CHECK)
  //   cfg: oldComptroller = comptroller
  //   cfg: require(bool,string)(newComptroller.isComptroller(),marker method returned false)
  //   cfg: comptroller = newComptroller
  //   cfg: NewComptroller(oldComptroller,newComptroller)
  // MToken-setReserveFactorFresh-NewReserveFactor: 
  //   cfg: newReserveFactorMantissa > reserveFactorMaxMantissa
  //   cfg: oldReserveFactorMantissa = reserveFactorMantissa
  //   cfg: reserveFactorMantissa = newReserveFactorMantissa
  //   cfg: NewReserveFactor(oldReserveFactorMantissa,newReserveFactorMantissa)
  // MToken-addReservesFresh-ReservesAdded: transfer
  //   cfg: totalReservesNew = totalReserves + actualAddAmount
  //   cfg: require(bool,string)(totalReservesNew >= totalReserves,add reserves unexpected overflow)
  //   cfg: totalReserves = totalReservesNew
  //   cfg: ReservesAdded(msg.sender,actualAddAmount,totalReservesNew)
  // MToken-reduceReservesFresh-ReservesReduced: transfer
  //   cfg: reduceAmount > totalReserves
  //   cfg: totalReservesNew = totalReserves - reduceAmount
  //   cfg: require(bool,string)(totalReservesNew <= totalReserves,reduce reserves unexpected underflow)
  //   cfg: totalReserves = totalReservesNew
  //   cfg: ReservesReduced(admin,reduceAmount,totalReservesNew)
  // MToken-setInterestRateModelFresh-NewMarketInterestRateModel: 
  //   cfg: oldInterestRateModel = interestRateModel
  //   cfg: require(bool,string)(newInterestRateModel.isInterestRateModel(),marker method returned false)
  //   cfg: interestRateModel = newInterestRateModel
  //   cfg: NewMarketInterestRateModel(oldInterestRateModel,newInterestRateModel)
  // MToken-setProtocolSeizeShareFresh-NewProtocolSeizeShare: 
  //   cfg: oldProtocolSeizeShareMantissa = protocolSeizeShareMantissa
  //   cfg: protocolSeizeShareMantissa = newProtocolSeizeShareMantissa
  //   cfg: NewProtocolSeizeShare(oldProtocolSeizeShareMantissa,newProtocolSeizeShareMantissa)
  // ComptrollerErrorReporter-fail-Failure: 
  // ComptrollerErrorReporter-failOpaque-Failure: 
  // TokenErrorReporter-fail-Failure: 
  // TokenErrorReporter-failOpaque-Failure: 
  // ComptrollerErrorReporter-fail-Failure: 
  // ComptrollerErrorReporter-failOpaque-Failure: 
  // TokenErrorReporter-fail-Failure: 
  // TokenErrorReporter-failOpaque-Failure: 
  // ComptrollerErrorReporter-fail-Failure: 
  // ComptrollerErrorReporter-failOpaque-Failure: 
  // TokenErrorReporter-fail-Failure: 
  // TokenErrorReporter-failOpaque-Failure: 
  // MErc20Delegator-setImplementation-NewImplementation: 
  //   cfg: require(bool,string)(msg.sender == admin,MErc20Delegator::_setImplementation: Caller must be admin)
  //   cfg: delegateToImplementation(abi.encodeWithSignature(_resignImplementation()))
  //   cfg: oldImplementation = implementation
  //   cfg: implementation = implementation_
  //   cfg: delegateToImplementation(abi.encodeWithSignature(_becomeImplementation(bytes),becomeImplementationData))
  // ComptrollerErrorReporter-fail-Failure: 
  // ComptrollerErrorReporter-failOpaque-Failure: 
  // TokenErrorReporter-fail-Failure: 
  // TokenErrorReporter-failOpaque-Failure: 
  // ComptrollerErrorReporter-fail-Failure: 
  // ComptrollerErrorReporter-failOpaque-Failure: 
  // TokenErrorReporter-fail-Failure: 
  // TokenErrorReporter-failOpaque-Failure: 
  // ComptrollerErrorReporter-fail-Failure: 
  // ComptrollerErrorReporter-failOpaque-Failure: 
  // TokenErrorReporter-fail-Failure: 
  // TokenErrorReporter-failOpaque-Failure: 
  // MToken-transferTokens-Transfer: transfer
  //   cfg: startingAllowance = transferAllowances[src][spender]
  //   cfg: (mathErr,srcTokensNew) = subUInt(accountTokens[src],tokens)
  //   cfg: (mathErr,dstTokensNew) = addUInt(accountTokens[dst],tokens)
  //   cfg: accountTokens[src] = srcTokensNew
  //   cfg: accountTokens[dst] = dstTokensNew
  // MToken-approve-Approval: transfer
  //   cfg: transferAllowances[src][spender] = amount
  // MToken-accrueInterest-AccrueInterest: borrow
  //   cfg: accrualBlockTimestampPrior = accrualBlockTimestamp
  //   cfg: accrualBlockTimestampPrior == currentBlockTimestamp
  //   cfg: borrowsPrior = totalBorrows
  //   cfg: reservesPrior = totalReserves
  //   cfg: borrowIndexPrior = borrowIndex
  // MToken-mintFresh-Mint: mint, supply, transfer
  //   cfg: (vars.mathErr,vars.totalSupplyNew) = addUInt(totalSupply,vars.mintTokens)
  //   cfg: (vars.mathErr,vars.accountTokensNew) = addUInt(accountTokens[minter],vars.mintTokens)
  //   cfg: totalSupply = vars.totalSupplyNew
  //   cfg: accountTokens[minter] = vars.accountTokensNew
  // MToken-mintFresh-Transfer: mint, supply, transfer
  //   cfg: (vars.mathErr,vars.totalSupplyNew) = addUInt(totalSupply,vars.mintTokens)
  //   cfg: (vars.mathErr,vars.accountTokensNew) = addUInt(accountTokens[minter],vars.mintTokens)
  //   cfg: totalSupply = vars.totalSupplyNew
  //   cfg: accountTokens[minter] = vars.accountTokensNew
  // MToken-redeemFresh-Transfer: redeem, supply, transfer
  //   cfg: vars.redeemTokens = accountTokens[redeemer]
  //   cfg: (vars.mathErr,vars.totalSupplyNew) = subUInt(totalSupply,vars.redeemTokens)
  //   cfg: (vars.mathErr,vars.accountTokensNew) = subUInt(accountTokens[redeemer],vars.redeemTokens)
  //   cfg: totalSupply = vars.totalSupplyNew
  //   cfg: accountTokens[redeemer] = vars.accountTokensNew
  // MToken-redeemFresh-Redeem: redeem, supply, transfer
  //   cfg: vars.redeemTokens = accountTokens[redeemer]
  //   cfg: (vars.mathErr,vars.totalSupplyNew) = subUInt(totalSupply,vars.redeemTokens)
  //   cfg: (vars.mathErr,vars.accountTokensNew) = subUInt(accountTokens[redeemer],vars.redeemTokens)
  //   cfg: totalSupply = vars.totalSupplyNew
  //   cfg: accountTokens[redeemer] = vars.accountTokensNew
  // MToken-borrowFresh-Borrow: borrow, transfer
  //   cfg: (vars.mathErr,vars.accountBorrows) = borrowBalanceStoredInternal(borrower)
  //   cfg: (vars.mathErr,vars.accountBorrowsNew) = addUInt(vars.accountBorrows,borrowAmount)
  //   cfg: (vars.mathErr,vars.totalBorrowsNew) = addUInt(totalBorrows,borrowAmount)
  //   cfg: accountBorrows[borrower].principal = vars.accountBorrowsNew
  //   cfg: accountBorrows[borrower].interestIndex = borrowIndex
  // MToken-repayBorrowFresh-RepayBorrow: borrow, transfer
  //   cfg: vars.borrowerIndex = accountBorrows[borrower].interestIndex
  //   cfg: (vars.mathErr,vars.accountBorrows) = borrowBalanceStoredInternal(borrower)
  //   cfg: vars.repayAmount = vars.accountBorrows
  //   cfg: (vars.mathErr,vars.accountBorrowsNew) = subUInt(vars.accountBorrows,vars.actualRepayAmount)
  //   cfg: (vars.mathErr,vars.totalBorrowsNew) = subUInt(totalBorrows,vars.actualRepayAmount)
  // MToken-liquidateBorrowFresh-LiquidateBorrow: borrow, liquidate
  // MToken-seizeInternal-Transfer: borrow, liquidate, supply, transfer
  //   cfg: (vars.mathErr,vars.borrowerTokensNew) = subUInt(accountTokens[borrower],seizeTokens)
  //   cfg: vars.totalReservesNew = add_(totalReserves,vars.protocolSeizeAmount)
  //   cfg: vars.totalSupplyNew = sub_(totalSupply,vars.protocolSeizeTokens)
  //   cfg: (vars.mathErr,vars.liquidatorTokensNew) = addUInt(accountTokens[liquidator],vars.liquidatorSeizeTokens)
  //   cfg: totalReserves = vars.totalReservesNew
  // MToken-seizeInternal-Transfer: borrow, liquidate, supply, transfer
  //   cfg: (vars.mathErr,vars.borrowerTokensNew) = subUInt(accountTokens[borrower],seizeTokens)
  //   cfg: vars.totalReservesNew = add_(totalReserves,vars.protocolSeizeAmount)
  //   cfg: vars.totalSupplyNew = sub_(totalSupply,vars.protocolSeizeTokens)
  //   cfg: (vars.mathErr,vars.liquidatorTokensNew) = addUInt(accountTokens[liquidator],vars.liquidatorSeizeTokens)
  //   cfg: totalReserves = vars.totalReservesNew
  // MToken-seizeInternal-ReservesAdded: borrow, liquidate, supply, transfer
  //   cfg: (vars.mathErr,vars.borrowerTokensNew) = subUInt(accountTokens[borrower],seizeTokens)
  //   cfg: vars.totalReservesNew = add_(totalReserves,vars.protocolSeizeAmount)
  //   cfg: vars.totalSupplyNew = sub_(totalSupply,vars.protocolSeizeTokens)
  //   cfg: (vars.mathErr,vars.liquidatorTokensNew) = addUInt(accountTokens[liquidator],vars.liquidatorSeizeTokens)
  //   cfg: totalReserves = vars.totalReservesNew
  // MToken-setPendingAdmin-NewPendingAdmin: 
  //   cfg: oldPendingAdmin = pendingAdmin
  //   cfg: pendingAdmin = newPendingAdmin
  //   cfg: NewPendingAdmin(oldPendingAdmin,newPendingAdmin)
  // MToken-acceptAdmin-NewAdmin: 
  //   cfg: msg.sender != pendingAdmin || msg.sender == address(0)
  //   cfg: fail(Error.UNAUTHORIZED,FailureInfo.ACCEPT_ADMIN_PENDING_ADMIN_CHECK)
  //   cfg: oldAdmin = admin
  //   cfg: oldPendingAdmin = pendingAdmin
  //   cfg: admin = pendingAdmin
  // MToken-acceptAdmin-NewPendingAdmin: 
  //   cfg: msg.sender != pendingAdmin || msg.sender == address(0)
  //   cfg: fail(Error.UNAUTHORIZED,FailureInfo.ACCEPT_ADMIN_PENDING_ADMIN_CHECK)
  //   cfg: oldAdmin = admin
  //   cfg: oldPendingAdmin = pendingAdmin
  //   cfg: admin = pendingAdmin
  // MToken-setComptroller-NewComptroller: 
  //   cfg: fail(Error.UNAUTHORIZED,FailureInfo.SET_COMPTROLLER_OWNER_CHECK)
  //   cfg: oldComptroller = comptroller
  //   cfg: require(bool,string)(newComptroller.isComptroller(),marker method returned false)
  //   cfg: comptroller = newComptroller
  //   cfg: NewComptroller(oldComptroller,newComptroller)
  // MToken-setReserveFactorFresh-NewReserveFactor: 
  //   cfg: newReserveFactorMantissa > reserveFactorMaxMantissa
  //   cfg: oldReserveFactorMantissa = reserveFactorMantissa
  //   cfg: reserveFactorMantissa = newReserveFactorMantissa
  //   cfg: NewReserveFactor(oldReserveFactorMantissa,newReserveFactorMantissa)
  // MToken-addReservesFresh-ReservesAdded: transfer
  //   cfg: totalReservesNew = totalReserves + actualAddAmount
  //   cfg: require(bool,string)(totalReservesNew >= totalReserves,add reserves unexpected overflow)
  //   cfg: totalReserves = totalReservesNew
  //   cfg: ReservesAdded(msg.sender,actualAddAmount,totalReservesNew)
  // MToken-reduceReservesFresh-ReservesReduced: transfer
  //   cfg: reduceAmount > totalReserves
  //   cfg: totalReservesNew = totalReserves - reduceAmount
  //   cfg: require(bool,string)(totalReservesNew <= totalReserves,reduce reserves unexpected underflow)
  //   cfg: totalReserves = totalReservesNew
  //   cfg: ReservesReduced(admin,reduceAmount,totalReservesNew)
  // MToken-setInterestRateModelFresh-NewMarketInterestRateModel: 
  //   cfg: oldInterestRateModel = interestRateModel
  //   cfg: require(bool,string)(newInterestRateModel.isInterestRateModel(),marker method returned false)
  //   cfg: interestRateModel = newInterestRateModel
  //   cfg: NewMarketInterestRateModel(oldInterestRateModel,newInterestRateModel)
  // MToken-setProtocolSeizeShareFresh-NewProtocolSeizeShare: 
  //   cfg: oldProtocolSeizeShareMantissa = protocolSeizeShareMantissa
  //   cfg: protocolSeizeShareMantissa = newProtocolSeizeShareMantissa
  //   cfg: NewProtocolSeizeShare(oldProtocolSeizeShareMantissa,newProtocolSeizeShareMantissa)
  // ComptrollerErrorReporter-fail-Failure: 
  // ComptrollerErrorReporter-failOpaque-Failure: 
  // TokenErrorReporter-fail-Failure: 
  // TokenErrorReporter-failOpaque-Failure: 
  // ComptrollerErrorReporter-fail-Failure: 
  // ComptrollerErrorReporter-failOpaque-Failure: 
  // TokenErrorReporter-fail-Failure: 
  // TokenErrorReporter-failOpaque-Failure: 
  // MToken-transferTokens-Transfer: transfer
  //   cfg: startingAllowance = transferAllowances[src][spender]
  //   cfg: (mathErr,srcTokensNew) = subUInt(accountTokens[src],tokens)
  //   cfg: (mathErr,dstTokensNew) = addUInt(accountTokens[dst],tokens)
  //   cfg: accountTokens[src] = srcTokensNew
  //   cfg: accountTokens[dst] = dstTokensNew
  // MToken-approve-Approval: transfer
  //   cfg: transferAllowances[src][spender] = amount
  // MToken-accrueInterest-AccrueInterest: borrow
  //   cfg: accrualBlockTimestampPrior = accrualBlockTimestamp
  //   cfg: accrualBlockTimestampPrior == currentBlockTimestamp
  //   cfg: borrowsPrior = totalBorrows
  //   cfg: reservesPrior = totalReserves
  //   cfg: borrowIndexPrior = borrowIndex
  // MToken-mintFresh-Mint: mint, supply, transfer
  //   cfg: (vars.mathErr,vars.totalSupplyNew) = addUInt(totalSupply,vars.mintTokens)
  //   cfg: (vars.mathErr,vars.accountTokensNew) = addUInt(accountTokens[minter],vars.mintTokens)
  //   cfg: totalSupply = vars.totalSupplyNew
  //   cfg: accountTokens[minter] = vars.accountTokensNew
  // MToken-mintFresh-Transfer: mint, supply, transfer
  //   cfg: (vars.mathErr,vars.totalSupplyNew) = addUInt(totalSupply,vars.mintTokens)
  //   cfg: (vars.mathErr,vars.accountTokensNew) = addUInt(accountTokens[minter],vars.mintTokens)
  //   cfg: totalSupply = vars.totalSupplyNew
  //   cfg: accountTokens[minter] = vars.accountTokensNew
  // MToken-redeemFresh-Transfer: redeem, supply, transfer
  //   cfg: vars.redeemTokens = accountTokens[redeemer]
  //   cfg: (vars.mathErr,vars.totalSupplyNew) = subUInt(totalSupply,vars.redeemTokens)
  //   cfg: (vars.mathErr,vars.accountTokensNew) = subUInt(accountTokens[redeemer],vars.redeemTokens)
  //   cfg: totalSupply = vars.totalSupplyNew
  //   cfg: accountTokens[redeemer] = vars.accountTokensNew
  // MToken-redeemFresh-Redeem: redeem, supply, transfer
  //   cfg: vars.redeemTokens = accountTokens[redeemer]
  //   cfg: (vars.mathErr,vars.totalSupplyNew) = subUInt(totalSupply,vars.redeemTokens)
  //   cfg: (vars.mathErr,vars.accountTokensNew) = subUInt(accountTokens[redeemer],vars.redeemTokens)
  //   cfg: totalSupply = vars.totalSupplyNew
  //   cfg: accountTokens[redeemer] = vars.accountTokensNew
  // MToken-borrowFresh-Borrow: borrow, transfer
  //   cfg: (vars.mathErr,vars.accountBorrows) = borrowBalanceStoredInternal(borrower)
  //   cfg: (vars.mathErr,vars.accountBorrowsNew) = addUInt(vars.accountBorrows,borrowAmount)
  //   cfg: (vars.mathErr,vars.totalBorrowsNew) = addUInt(totalBorrows,borrowAmount)
  //   cfg: accountBorrows[borrower].principal = vars.accountBorrowsNew
  //   cfg: accountBorrows[borrower].interestIndex = borrowIndex
  // MToken-repayBorrowFresh-RepayBorrow: borrow, transfer
  //   cfg: vars.borrowerIndex = accountBorrows[borrower].interestIndex
  //   cfg: (vars.mathErr,vars.accountBorrows) = borrowBalanceStoredInternal(borrower)
  //   cfg: vars.repayAmount = vars.accountBorrows
  //   cfg: (vars.mathErr,vars.accountBorrowsNew) = subUInt(vars.accountBorrows,vars.actualRepayAmount)
  //   cfg: (vars.mathErr,vars.totalBorrowsNew) = subUInt(totalBorrows,vars.actualRepayAmount)
  // MToken-liquidateBorrowFresh-LiquidateBorrow: borrow, liquidate
  // MToken-seizeInternal-Transfer: borrow, liquidate, supply, transfer
  //   cfg: (vars.mathErr,vars.borrowerTokensNew) = subUInt(accountTokens[borrower],seizeTokens)
  //   cfg: vars.totalReservesNew = add_(totalReserves,vars.protocolSeizeAmount)
  //   cfg: vars.totalSupplyNew = sub_(totalSupply,vars.protocolSeizeTokens)
  //   cfg: (vars.mathErr,vars.liquidatorTokensNew) = addUInt(accountTokens[liquidator],vars.liquidatorSeizeTokens)
  //   cfg: totalReserves = vars.totalReservesNew
  // MToken-seizeInternal-Transfer: borrow, liquidate, supply, transfer
  //   cfg: (vars.mathErr,vars.borrowerTokensNew) = subUInt(accountTokens[borrower],seizeTokens)
  //   cfg: vars.totalReservesNew = add_(totalReserves,vars.protocolSeizeAmount)
  //   cfg: vars.totalSupplyNew = sub_(totalSupply,vars.protocolSeizeTokens)
  //   cfg: (vars.mathErr,vars.liquidatorTokensNew) = addUInt(accountTokens[liquidator],vars.liquidatorSeizeTokens)
  //   cfg: totalReserves = vars.totalReservesNew
  // MToken-seizeInternal-ReservesAdded: borrow, liquidate, supply, transfer
  //   cfg: (vars.mathErr,vars.borrowerTokensNew) = subUInt(accountTokens[borrower],seizeTokens)
  //   cfg: vars.totalReservesNew = add_(totalReserves,vars.protocolSeizeAmount)
  //   cfg: vars.totalSupplyNew = sub_(totalSupply,vars.protocolSeizeTokens)
  //   cfg: (vars.mathErr,vars.liquidatorTokensNew) = addUInt(accountTokens[liquidator],vars.liquidatorSeizeTokens)
  //   cfg: totalReserves = vars.totalReservesNew
  // MToken-setPendingAdmin-NewPendingAdmin: 
  //   cfg: oldPendingAdmin = pendingAdmin
  //   cfg: pendingAdmin = newPendingAdmin
  //   cfg: NewPendingAdmin(oldPendingAdmin,newPendingAdmin)
  // MToken-acceptAdmin-NewAdmin: 
  //   cfg: msg.sender != pendingAdmin || msg.sender == address(0)
  //   cfg: fail(Error.UNAUTHORIZED,FailureInfo.ACCEPT_ADMIN_PENDING_ADMIN_CHECK)
  //   cfg: oldAdmin = admin
  //   cfg: oldPendingAdmin = pendingAdmin
  //   cfg: admin = pendingAdmin
  // MToken-acceptAdmin-NewPendingAdmin: 
  //   cfg: msg.sender != pendingAdmin || msg.sender == address(0)
  //   cfg: fail(Error.UNAUTHORIZED,FailureInfo.ACCEPT_ADMIN_PENDING_ADMIN_CHECK)
  //   cfg: oldAdmin = admin
  //   cfg: oldPendingAdmin = pendingAdmin
  //   cfg: admin = pendingAdmin
  // MToken-setComptroller-NewComptroller: 
  //   cfg: fail(Error.UNAUTHORIZED,FailureInfo.SET_COMPTROLLER_OWNER_CHECK)
  //   cfg: oldComptroller = comptroller
  //   cfg: require(bool,string)(newComptroller.isComptroller(),marker method returned false)
  //   cfg: comptroller = newComptroller
  //   cfg: NewComptroller(oldComptroller,newComptroller)
  // MToken-setReserveFactorFresh-NewReserveFactor: 
  //   cfg: newReserveFactorMantissa > reserveFactorMaxMantissa
  //   cfg: oldReserveFactorMantissa = reserveFactorMantissa
  //   cfg: reserveFactorMantissa = newReserveFactorMantissa
  //   cfg: NewReserveFactor(oldReserveFactorMantissa,newReserveFactorMantissa)
  // MToken-addReservesFresh-ReservesAdded: transfer
  //   cfg: totalReservesNew = totalReserves + actualAddAmount
  //   cfg: require(bool,string)(totalReservesNew >= totalReserves,add reserves unexpected overflow)
  //   cfg: totalReserves = totalReservesNew
  //   cfg: ReservesAdded(msg.sender,actualAddAmount,totalReservesNew)
  // MToken-reduceReservesFresh-ReservesReduced: transfer
  //   cfg: reduceAmount > totalReserves
  //   cfg: totalReservesNew = totalReserves - reduceAmount
  //   cfg: require(bool,string)(totalReservesNew <= totalReserves,reduce reserves unexpected underflow)
  //   cfg: totalReserves = totalReservesNew
  //   cfg: ReservesReduced(admin,reduceAmount,totalReservesNew)
  // MToken-setInterestRateModelFresh-NewMarketInterestRateModel: 
  //   cfg: oldInterestRateModel = interestRateModel
  //   cfg: require(bool,string)(newInterestRateModel.isInterestRateModel(),marker method returned false)
  //   cfg: interestRateModel = newInterestRateModel
  //   cfg: NewMarketInterestRateModel(oldInterestRateModel,newInterestRateModel)
  // MToken-setProtocolSeizeShareFresh-NewProtocolSeizeShare: 
  //   cfg: oldProtocolSeizeShareMantissa = protocolSeizeShareMantissa
  //   cfg: protocolSeizeShareMantissa = newProtocolSeizeShareMantissa
  //   cfg: NewProtocolSeizeShare(oldProtocolSeizeShareMantissa,newProtocolSeizeShareMantissa)
endmodule
