requires "domains.md"

module DSC-GUARD-VENUS-LUNA-SYNTAX
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

module DSC-GUARD-VENUS-LUNA
  imports DSC-GUARD-VENUS-LUNA-SYNTAX
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
  // constraint LUNA_ORACLE_MUST_BE_FRESH: type=stale_oracle severity=critical
  // constraint LUNA_COLLATERAL_DISABLED_WHEN_STALE: type=stale_collateral_borrow severity=critical

  // Slither-mined event semantics.
  // ComptrollerErrorReporter-fail-Failure: 
  // ComptrollerErrorReporter-failOpaque-Failure: 
  // TokenErrorReporter-fail-Failure: 
  // TokenErrorReporter-failOpaque-Failure: 
  // VAIControllerErrorReporter-fail-Failure: 
  // VAIControllerErrorReporter-failOpaque-Failure: 
  // ComptrollerErrorReporter-fail-Failure: 
  // ComptrollerErrorReporter-failOpaque-Failure: 
  // TokenErrorReporter-fail-Failure: 
  // TokenErrorReporter-failOpaque-Failure: 
  // VAIControllerErrorReporter-fail-Failure: 
  // VAIControllerErrorReporter-failOpaque-Failure: 
  // VToken-transferTokens-Transfer: transfer
  //   cfg: startingAllowance = transferAllowances[src][spender]
  //   cfg: (mathErr,srvTokensNew) = subUInt(accountTokens[src],tokens)
  //   cfg: (mathErr,dstTokensNew) = addUInt(accountTokens[dst],tokens)
  //   cfg: accountTokens[src] = srvTokensNew
  //   cfg: accountTokens[dst] = dstTokensNew
  // VToken-approve-Approval: transfer
  //   cfg: transferAllowances[src][spender] = amount
  // VToken-accrueInterest-AccrueInterest: borrow
  //   cfg: accrualBlockNumberPrior = accrualBlockNumber
  //   cfg: accrualBlockNumberPrior == currentBlockNumber
  //   cfg: borrowsPrior = totalBorrows
  //   cfg: reservesPrior = totalReserves
  //   cfg: borrowIndexPrior = borrowIndex
  // VToken-mintFresh-Mint: mint, supply, transfer
  //   cfg: (vars.mathErr,vars.totalSupplyNew) = addUInt(totalSupply,vars.mintTokens)
  //   cfg: (vars.mathErr,vars.accountTokensNew) = addUInt(accountTokens[minter],vars.mintTokens)
  //   cfg: totalSupply = vars.totalSupplyNew
  //   cfg: accountTokens[minter] = vars.accountTokensNew
  // VToken-mintFresh-Transfer: mint, supply, transfer
  //   cfg: (vars.mathErr,vars.totalSupplyNew) = addUInt(totalSupply,vars.mintTokens)
  //   cfg: (vars.mathErr,vars.accountTokensNew) = addUInt(accountTokens[minter],vars.mintTokens)
  //   cfg: totalSupply = vars.totalSupplyNew
  //   cfg: accountTokens[minter] = vars.accountTokensNew
  // VToken-redeemFresh-RedeemFee: redeem, supply, transfer
  //   cfg: (vars.mathErr,vars.totalSupplyNew) = subUInt(totalSupply,vars.redeemTokens)
  //   cfg: (vars.mathErr,vars.accountTokensNew) = subUInt(accountTokens[redeemer],vars.redeemTokens)
  //   cfg: totalSupply = vars.totalSupplyNew
  //   cfg: accountTokens[redeemer] = vars.accountTokensNew
  // VToken-redeemFresh-Transfer: redeem, supply, transfer
  //   cfg: (vars.mathErr,vars.totalSupplyNew) = subUInt(totalSupply,vars.redeemTokens)
  //   cfg: (vars.mathErr,vars.accountTokensNew) = subUInt(accountTokens[redeemer],vars.redeemTokens)
  //   cfg: totalSupply = vars.totalSupplyNew
  //   cfg: accountTokens[redeemer] = vars.accountTokensNew
  // VToken-redeemFresh-Redeem: redeem, supply, transfer
  //   cfg: (vars.mathErr,vars.totalSupplyNew) = subUInt(totalSupply,vars.redeemTokens)
  //   cfg: (vars.mathErr,vars.accountTokensNew) = subUInt(accountTokens[redeemer],vars.redeemTokens)
  //   cfg: totalSupply = vars.totalSupplyNew
  //   cfg: accountTokens[redeemer] = vars.accountTokensNew
  // VToken-borrowFresh-Borrow: borrow, transfer
  //   cfg: (vars.mathErr,vars.accountBorrows) = borrowBalanceStoredInternal(borrower)
  //   cfg: (vars.mathErr,vars.accountBorrowsNew) = addUInt(vars.accountBorrows,borrowAmount)
  //   cfg: (vars.mathErr,vars.totalBorrowsNew) = addUInt(totalBorrows,borrowAmount)
  //   cfg: accountBorrows[borrower].principal = vars.accountBorrowsNew
  //   cfg: accountBorrows[borrower].interestIndex = borrowIndex
  // VToken-repayBorrowFresh-RepayBorrow: borrow, transfer
  //   cfg: vars.borrowerIndex = accountBorrows[borrower].interestIndex
  //   cfg: (vars.mathErr,vars.accountBorrows) = borrowBalanceStoredInternal(borrower)
  //   cfg: vars.repayAmount = vars.accountBorrows
  //   cfg: (vars.mathErr,vars.accountBorrowsNew) = subUInt(vars.accountBorrows,vars.actualRepayAmount)
  //   cfg: (vars.mathErr,vars.totalBorrowsNew) = subUInt(totalBorrows,vars.actualRepayAmount)
  // VToken-liquidateBorrowFresh-LiquidateBorrow: borrow, liquidate
  // VToken-seizeInternal-Transfer: borrow, liquidate, transfer
  //   cfg: (mathErr,borrowerTokensNew) = subUInt(accountTokens[borrower],seizeTokens)
  //   cfg: (mathErr,liquidatorTokensNew) = addUInt(accountTokens[liquidator],seizeTokens)
  //   cfg: accountTokens[borrower] = borrowerTokensNew
  //   cfg: accountTokens[liquidator] = liquidatorTokensNew
  // VToken-setPendingAdmin-NewPendingAdmin: 
  //   cfg: oldPendingAdmin = pendingAdmin
  //   cfg: pendingAdmin = newPendingAdmin
  //   cfg: NewPendingAdmin(oldPendingAdmin,newPendingAdmin)
  // VToken-acceptAdmin-NewAdmin: 
  //   cfg: msg.sender != pendingAdmin || msg.sender == address(0)
  //   cfg: fail(Error.UNAUTHORIZED,FailureInfo.ACCEPT_ADMIN_PENDING_ADMIN_CHECK)
  //   cfg: oldAdmin = admin
  //   cfg: oldPendingAdmin = pendingAdmin
  //   cfg: admin = pendingAdmin
  // VToken-acceptAdmin-NewPendingAdmin: 
  //   cfg: msg.sender != pendingAdmin || msg.sender == address(0)
  //   cfg: fail(Error.UNAUTHORIZED,FailureInfo.ACCEPT_ADMIN_PENDING_ADMIN_CHECK)
  //   cfg: oldAdmin = admin
  //   cfg: oldPendingAdmin = pendingAdmin
  //   cfg: admin = pendingAdmin
  // VToken-setComptroller-NewComptroller: 
  //   cfg: fail(Error.UNAUTHORIZED,FailureInfo.SET_COMPTROLLER_OWNER_CHECK)
  //   cfg: oldComptroller = comptroller
  //   cfg: require(bool,string)(newComptroller.isComptroller(),marker method returned false)
  //   cfg: comptroller = newComptroller
  //   cfg: NewComptroller(oldComptroller,newComptroller)
  // VToken-setReserveFactorFresh-NewReserveFactor: 
  //   cfg: newReserveFactorMantissa > reserveFactorMaxMantissa
  //   cfg: oldReserveFactorMantissa = reserveFactorMantissa
  //   cfg: reserveFactorMantissa = newReserveFactorMantissa
  //   cfg: NewReserveFactor(oldReserveFactorMantissa,newReserveFactorMantissa)
  // VToken-addReservesFresh-ReservesAdded: transfer
  //   cfg: totalReservesNew = totalReserves + actualAddAmount
  //   cfg: require(bool,string)(totalReservesNew >= totalReserves,add reserves unexpected overflow)
  //   cfg: totalReserves = totalReservesNew
  //   cfg: ReservesAdded(msg.sender,actualAddAmount,totalReservesNew)
  // VToken-reduceReservesFresh-ReservesReduced: transfer
  //   cfg: reduceAmount > totalReserves
  //   cfg: totalReservesNew = totalReserves - reduceAmount
  //   cfg: require(bool,string)(totalReservesNew <= totalReserves,reduce reserves unexpected underflow)
  //   cfg: totalReserves = totalReservesNew
  //   cfg: ReservesReduced(admin,reduceAmount,totalReservesNew)
  // VToken-setInterestRateModelFresh-NewMarketInterestRateModel: 
  //   cfg: oldInterestRateModel = interestRateModel
  //   cfg: require(bool,string)(newInterestRateModel.isInterestRateModel(),marker method returned false)
  //   cfg: interestRateModel = newInterestRateModel
  //   cfg: NewMarketInterestRateModel(oldInterestRateModel,newInterestRateModel)
  // ComptrollerErrorReporter-fail-Failure: 
  // ComptrollerErrorReporter-failOpaque-Failure: 
  // TokenErrorReporter-fail-Failure: 
  // TokenErrorReporter-failOpaque-Failure: 
  // VAIControllerErrorReporter-fail-Failure: 
  // VAIControllerErrorReporter-failOpaque-Failure: 
  // VToken-transferTokens-Transfer: transfer
  //   cfg: startingAllowance = transferAllowances[src][spender]
  //   cfg: (mathErr,srvTokensNew) = subUInt(accountTokens[src],tokens)
  //   cfg: (mathErr,dstTokensNew) = addUInt(accountTokens[dst],tokens)
  //   cfg: accountTokens[src] = srvTokensNew
  //   cfg: accountTokens[dst] = dstTokensNew
  // VToken-approve-Approval: transfer
  //   cfg: transferAllowances[src][spender] = amount
  // VToken-accrueInterest-AccrueInterest: borrow
  //   cfg: accrualBlockNumberPrior = accrualBlockNumber
  //   cfg: accrualBlockNumberPrior == currentBlockNumber
  //   cfg: borrowsPrior = totalBorrows
  //   cfg: reservesPrior = totalReserves
  //   cfg: borrowIndexPrior = borrowIndex
  // VToken-mintFresh-Mint: mint, supply, transfer
  //   cfg: (vars.mathErr,vars.totalSupplyNew) = addUInt(totalSupply,vars.mintTokens)
  //   cfg: (vars.mathErr,vars.accountTokensNew) = addUInt(accountTokens[minter],vars.mintTokens)
  //   cfg: totalSupply = vars.totalSupplyNew
  //   cfg: accountTokens[minter] = vars.accountTokensNew
  // VToken-mintFresh-Transfer: mint, supply, transfer
  //   cfg: (vars.mathErr,vars.totalSupplyNew) = addUInt(totalSupply,vars.mintTokens)
  //   cfg: (vars.mathErr,vars.accountTokensNew) = addUInt(accountTokens[minter],vars.mintTokens)
  //   cfg: totalSupply = vars.totalSupplyNew
  //   cfg: accountTokens[minter] = vars.accountTokensNew
  // VToken-redeemFresh-RedeemFee: redeem, supply, transfer
  //   cfg: (vars.mathErr,vars.totalSupplyNew) = subUInt(totalSupply,vars.redeemTokens)
  //   cfg: (vars.mathErr,vars.accountTokensNew) = subUInt(accountTokens[redeemer],vars.redeemTokens)
  //   cfg: totalSupply = vars.totalSupplyNew
  //   cfg: accountTokens[redeemer] = vars.accountTokensNew
  // VToken-redeemFresh-Transfer: redeem, supply, transfer
  //   cfg: (vars.mathErr,vars.totalSupplyNew) = subUInt(totalSupply,vars.redeemTokens)
  //   cfg: (vars.mathErr,vars.accountTokensNew) = subUInt(accountTokens[redeemer],vars.redeemTokens)
  //   cfg: totalSupply = vars.totalSupplyNew
  //   cfg: accountTokens[redeemer] = vars.accountTokensNew
  // VToken-redeemFresh-Redeem: redeem, supply, transfer
  //   cfg: (vars.mathErr,vars.totalSupplyNew) = subUInt(totalSupply,vars.redeemTokens)
  //   cfg: (vars.mathErr,vars.accountTokensNew) = subUInt(accountTokens[redeemer],vars.redeemTokens)
  //   cfg: totalSupply = vars.totalSupplyNew
  //   cfg: accountTokens[redeemer] = vars.accountTokensNew
  // VToken-borrowFresh-Borrow: borrow, transfer
  //   cfg: (vars.mathErr,vars.accountBorrows) = borrowBalanceStoredInternal(borrower)
  //   cfg: (vars.mathErr,vars.accountBorrowsNew) = addUInt(vars.accountBorrows,borrowAmount)
  //   cfg: (vars.mathErr,vars.totalBorrowsNew) = addUInt(totalBorrows,borrowAmount)
  //   cfg: accountBorrows[borrower].principal = vars.accountBorrowsNew
  //   cfg: accountBorrows[borrower].interestIndex = borrowIndex
  // VToken-repayBorrowFresh-RepayBorrow: borrow, transfer
  //   cfg: vars.borrowerIndex = accountBorrows[borrower].interestIndex
  //   cfg: (vars.mathErr,vars.accountBorrows) = borrowBalanceStoredInternal(borrower)
  //   cfg: vars.repayAmount = vars.accountBorrows
  //   cfg: (vars.mathErr,vars.accountBorrowsNew) = subUInt(vars.accountBorrows,vars.actualRepayAmount)
  //   cfg: (vars.mathErr,vars.totalBorrowsNew) = subUInt(totalBorrows,vars.actualRepayAmount)
  // VToken-liquidateBorrowFresh-LiquidateBorrow: borrow, liquidate
  // VToken-seizeInternal-Transfer: borrow, liquidate, transfer
  //   cfg: (mathErr,borrowerTokensNew) = subUInt(accountTokens[borrower],seizeTokens)
  //   cfg: (mathErr,liquidatorTokensNew) = addUInt(accountTokens[liquidator],seizeTokens)
  //   cfg: accountTokens[borrower] = borrowerTokensNew
  //   cfg: accountTokens[liquidator] = liquidatorTokensNew
  // VToken-setPendingAdmin-NewPendingAdmin: 
  //   cfg: oldPendingAdmin = pendingAdmin
  //   cfg: pendingAdmin = newPendingAdmin
  //   cfg: NewPendingAdmin(oldPendingAdmin,newPendingAdmin)
  // VToken-acceptAdmin-NewAdmin: 
  //   cfg: msg.sender != pendingAdmin || msg.sender == address(0)
  //   cfg: fail(Error.UNAUTHORIZED,FailureInfo.ACCEPT_ADMIN_PENDING_ADMIN_CHECK)
  //   cfg: oldAdmin = admin
  //   cfg: oldPendingAdmin = pendingAdmin
  //   cfg: admin = pendingAdmin
  // VToken-acceptAdmin-NewPendingAdmin: 
  //   cfg: msg.sender != pendingAdmin || msg.sender == address(0)
  //   cfg: fail(Error.UNAUTHORIZED,FailureInfo.ACCEPT_ADMIN_PENDING_ADMIN_CHECK)
  //   cfg: oldAdmin = admin
  //   cfg: oldPendingAdmin = pendingAdmin
  //   cfg: admin = pendingAdmin
  // VToken-setComptroller-NewComptroller: 
  //   cfg: fail(Error.UNAUTHORIZED,FailureInfo.SET_COMPTROLLER_OWNER_CHECK)
  //   cfg: oldComptroller = comptroller
  //   cfg: require(bool,string)(newComptroller.isComptroller(),marker method returned false)
  //   cfg: comptroller = newComptroller
  //   cfg: NewComptroller(oldComptroller,newComptroller)
  // VToken-setReserveFactorFresh-NewReserveFactor: 
  //   cfg: newReserveFactorMantissa > reserveFactorMaxMantissa
  //   cfg: oldReserveFactorMantissa = reserveFactorMantissa
  //   cfg: reserveFactorMantissa = newReserveFactorMantissa
  //   cfg: NewReserveFactor(oldReserveFactorMantissa,newReserveFactorMantissa)
  // VToken-addReservesFresh-ReservesAdded: transfer
  //   cfg: totalReservesNew = totalReserves + actualAddAmount
  //   cfg: require(bool,string)(totalReservesNew >= totalReserves,add reserves unexpected overflow)
  //   cfg: totalReserves = totalReservesNew
  //   cfg: ReservesAdded(msg.sender,actualAddAmount,totalReservesNew)
  // VToken-reduceReservesFresh-ReservesReduced: transfer
  //   cfg: reduceAmount > totalReserves
  //   cfg: totalReservesNew = totalReserves - reduceAmount
  //   cfg: require(bool,string)(totalReservesNew <= totalReserves,reduce reserves unexpected underflow)
  //   cfg: totalReserves = totalReservesNew
  //   cfg: ReservesReduced(admin,reduceAmount,totalReservesNew)
  // VToken-setInterestRateModelFresh-NewMarketInterestRateModel: 
  //   cfg: oldInterestRateModel = interestRateModel
  //   cfg: require(bool,string)(newInterestRateModel.isInterestRateModel(),marker method returned false)
  //   cfg: interestRateModel = newInterestRateModel
  //   cfg: NewMarketInterestRateModel(oldInterestRateModel,newInterestRateModel)
  // ComptrollerErrorReporter-fail-Failure: 
  // ComptrollerErrorReporter-failOpaque-Failure: 
  // TokenErrorReporter-fail-Failure: 
  // TokenErrorReporter-failOpaque-Failure: 
  // VAIControllerErrorReporter-fail-Failure: 
  // VAIControllerErrorReporter-failOpaque-Failure: 
  // VToken-transferTokens-Transfer: transfer
  //   cfg: startingAllowance = transferAllowances[src][spender]
  //   cfg: (mathErr,srvTokensNew) = subUInt(accountTokens[src],tokens)
  //   cfg: (mathErr,dstTokensNew) = addUInt(accountTokens[dst],tokens)
  //   cfg: accountTokens[src] = srvTokensNew
  //   cfg: accountTokens[dst] = dstTokensNew
  // VToken-approve-Approval: transfer
  //   cfg: transferAllowances[src][spender] = amount
  // VToken-accrueInterest-AccrueInterest: borrow
  //   cfg: accrualBlockNumberPrior = accrualBlockNumber
  //   cfg: accrualBlockNumberPrior == currentBlockNumber
  //   cfg: borrowsPrior = totalBorrows
  //   cfg: reservesPrior = totalReserves
  //   cfg: borrowIndexPrior = borrowIndex
  // VToken-mintFresh-Mint: mint, supply, transfer
  //   cfg: (vars.mathErr,vars.totalSupplyNew) = addUInt(totalSupply,vars.mintTokens)
  //   cfg: (vars.mathErr,vars.accountTokensNew) = addUInt(accountTokens[minter],vars.mintTokens)
  //   cfg: totalSupply = vars.totalSupplyNew
  //   cfg: accountTokens[minter] = vars.accountTokensNew
  // VToken-mintFresh-Transfer: mint, supply, transfer
  //   cfg: (vars.mathErr,vars.totalSupplyNew) = addUInt(totalSupply,vars.mintTokens)
  //   cfg: (vars.mathErr,vars.accountTokensNew) = addUInt(accountTokens[minter],vars.mintTokens)
  //   cfg: totalSupply = vars.totalSupplyNew
  //   cfg: accountTokens[minter] = vars.accountTokensNew
  // VToken-redeemFresh-RedeemFee: redeem, supply, transfer
  //   cfg: (vars.mathErr,vars.totalSupplyNew) = subUInt(totalSupply,vars.redeemTokens)
  //   cfg: (vars.mathErr,vars.accountTokensNew) = subUInt(accountTokens[redeemer],vars.redeemTokens)
  //   cfg: totalSupply = vars.totalSupplyNew
  //   cfg: accountTokens[redeemer] = vars.accountTokensNew
  // VToken-redeemFresh-Transfer: redeem, supply, transfer
  //   cfg: (vars.mathErr,vars.totalSupplyNew) = subUInt(totalSupply,vars.redeemTokens)
  //   cfg: (vars.mathErr,vars.accountTokensNew) = subUInt(accountTokens[redeemer],vars.redeemTokens)
  //   cfg: totalSupply = vars.totalSupplyNew
  //   cfg: accountTokens[redeemer] = vars.accountTokensNew
  // VToken-redeemFresh-Redeem: redeem, supply, transfer
  //   cfg: (vars.mathErr,vars.totalSupplyNew) = subUInt(totalSupply,vars.redeemTokens)
  //   cfg: (vars.mathErr,vars.accountTokensNew) = subUInt(accountTokens[redeemer],vars.redeemTokens)
  //   cfg: totalSupply = vars.totalSupplyNew
  //   cfg: accountTokens[redeemer] = vars.accountTokensNew
  // VToken-borrowFresh-Borrow: borrow, transfer
  //   cfg: (vars.mathErr,vars.accountBorrows) = borrowBalanceStoredInternal(borrower)
  //   cfg: (vars.mathErr,vars.accountBorrowsNew) = addUInt(vars.accountBorrows,borrowAmount)
  //   cfg: (vars.mathErr,vars.totalBorrowsNew) = addUInt(totalBorrows,borrowAmount)
  //   cfg: accountBorrows[borrower].principal = vars.accountBorrowsNew
  //   cfg: accountBorrows[borrower].interestIndex = borrowIndex
  // VToken-repayBorrowFresh-RepayBorrow: borrow, transfer
  //   cfg: vars.borrowerIndex = accountBorrows[borrower].interestIndex
  //   cfg: (vars.mathErr,vars.accountBorrows) = borrowBalanceStoredInternal(borrower)
  //   cfg: vars.repayAmount = vars.accountBorrows
  //   cfg: (vars.mathErr,vars.accountBorrowsNew) = subUInt(vars.accountBorrows,vars.actualRepayAmount)
  //   cfg: (vars.mathErr,vars.totalBorrowsNew) = subUInt(totalBorrows,vars.actualRepayAmount)
  // VToken-liquidateBorrowFresh-LiquidateBorrow: borrow, liquidate
  // VToken-seizeInternal-Transfer: borrow, liquidate, transfer
  //   cfg: (mathErr,borrowerTokensNew) = subUInt(accountTokens[borrower],seizeTokens)
  //   cfg: (mathErr,liquidatorTokensNew) = addUInt(accountTokens[liquidator],seizeTokens)
  //   cfg: accountTokens[borrower] = borrowerTokensNew
  //   cfg: accountTokens[liquidator] = liquidatorTokensNew
  // VToken-setPendingAdmin-NewPendingAdmin: 
  //   cfg: oldPendingAdmin = pendingAdmin
  //   cfg: pendingAdmin = newPendingAdmin
  //   cfg: NewPendingAdmin(oldPendingAdmin,newPendingAdmin)
  // VToken-acceptAdmin-NewAdmin: 
  //   cfg: msg.sender != pendingAdmin || msg.sender == address(0)
  //   cfg: fail(Error.UNAUTHORIZED,FailureInfo.ACCEPT_ADMIN_PENDING_ADMIN_CHECK)
  //   cfg: oldAdmin = admin
  //   cfg: oldPendingAdmin = pendingAdmin
  //   cfg: admin = pendingAdmin
  // VToken-acceptAdmin-NewPendingAdmin: 
  //   cfg: msg.sender != pendingAdmin || msg.sender == address(0)
  //   cfg: fail(Error.UNAUTHORIZED,FailureInfo.ACCEPT_ADMIN_PENDING_ADMIN_CHECK)
  //   cfg: oldAdmin = admin
  //   cfg: oldPendingAdmin = pendingAdmin
  //   cfg: admin = pendingAdmin
  // VToken-setComptroller-NewComptroller: 
  //   cfg: fail(Error.UNAUTHORIZED,FailureInfo.SET_COMPTROLLER_OWNER_CHECK)
  //   cfg: oldComptroller = comptroller
  //   cfg: require(bool,string)(newComptroller.isComptroller(),marker method returned false)
  //   cfg: comptroller = newComptroller
  //   cfg: NewComptroller(oldComptroller,newComptroller)
  // VToken-setReserveFactorFresh-NewReserveFactor: 
  //   cfg: newReserveFactorMantissa > reserveFactorMaxMantissa
  //   cfg: oldReserveFactorMantissa = reserveFactorMantissa
  //   cfg: reserveFactorMantissa = newReserveFactorMantissa
  //   cfg: NewReserveFactor(oldReserveFactorMantissa,newReserveFactorMantissa)
  // VToken-addReservesFresh-ReservesAdded: transfer
  //   cfg: totalReservesNew = totalReserves + actualAddAmount
  //   cfg: require(bool,string)(totalReservesNew >= totalReserves,add reserves unexpected overflow)
  //   cfg: totalReserves = totalReservesNew
  //   cfg: ReservesAdded(msg.sender,actualAddAmount,totalReservesNew)
  // VToken-reduceReservesFresh-ReservesReduced: transfer
  //   cfg: reduceAmount > totalReserves
  //   cfg: totalReservesNew = totalReserves - reduceAmount
  //   cfg: require(bool,string)(totalReservesNew <= totalReserves,reduce reserves unexpected underflow)
  //   cfg: totalReserves = totalReservesNew
  //   cfg: ReservesReduced(admin,reduceAmount,totalReservesNew)
  // VToken-setInterestRateModelFresh-NewMarketInterestRateModel: 
  //   cfg: oldInterestRateModel = interestRateModel
  //   cfg: require(bool,string)(newInterestRateModel.isInterestRateModel(),marker method returned false)
  //   cfg: interestRateModel = newInterestRateModel
  //   cfg: NewMarketInterestRateModel(oldInterestRateModel,newInterestRateModel)
  // VBep20Delegator-setImplementation-NewImplementation: 
  //   cfg: require(bool,string)(msg.sender == admin,VBep20Delegator::_setImplementation: Caller must be admin)
  //   cfg: delegateToImplementation(abi.encodeWithSignature(_resignImplementation()))
  //   cfg: oldImplementation = implementation
  //   cfg: implementation = implementation_
  //   cfg: delegateToImplementation(abi.encodeWithSignature(_becomeImplementation(bytes),becomeImplementationData))
  // AccessControlTestHelper-readGetRoundData-Dummy: 
  // AccessControlTestHelper-readLatestRoundData-Dummy: oracle-read
  //   cfg: AccessControlledOffchainAggregator(_aggregator).latestRoundData()
  // AccessControlTestHelper-readLatestAnswer-Dummy: oracle-read
  //   cfg: AccessControlledOffchainAggregator(_aggregator).latestAnswer()
  // AccessControlTestHelper-readLatestTimestamp-Dummy: 
  // AccessControlTestHelper-readLatestRound-Dummy: 
  // AccessControlTestHelper-readGetAnswer-Dummy: 
  // AccessControlTestHelper-readGetTimestamp-Dummy: 
  // OffchainAggregator-setConfig-ConfigSet: oracle-read, oracle-setter
  //   cfg: payOracle(transmitter)
  //   cfg: delete s_oracles[signer]
  //   cfg: delete s_oracles[transmitter]
  //   cfg: require(bool,string)(s_oracles[_signers[i]].role == Role.Unset,repeated signer address)
  //   cfg: s_oracles[_signers[i]] = Oracle(uint8(i),Role.Signer)
  // OffchainAggregator-setValidatorConfig-ValidatorConfigSet: 
  //   cfg: previous = s_validatorConfig
  //   cfg: s_validatorConfig = ValidatorConfig({validator:_newValidator,gasLimit:_newGasLimit})
  // OffchainAggregator-setRequesterAccessController-RequesterAccessControllerSet: 
  //   cfg: oldController = s_requesterAccessController
  //   cfg: s_requesterAccessController = AccessControllerInterface(_requesterAccessController)
  // OffchainAggregator-requestNewRound-RoundRequested: 
  // OffchainAggregator-transmit-NewTransmission: freshness-check, oracle-read
  //   cfg: require(bool,string)(r.hotVars.latestEpochAndRound < epochAndRound,stale report)
  //   cfg: require(bool,string)(_rs.length <= maxNumOracles,too many signatures)
  //   cfg: require(bool,string)(r.observations.length <= maxNumOracles,num observations out of bounds)
  //   cfg: transmitter = s_oracles[msg.sender]
  //   cfg: o = s_oracles[signer]
  // OffchainAggregator-transmit-NewRound: freshness-check, oracle-read
  //   cfg: require(bool,string)(r.hotVars.latestEpochAndRound < epochAndRound,stale report)
  //   cfg: require(bool,string)(_rs.length <= maxNumOracles,too many signatures)
  //   cfg: require(bool,string)(r.observations.length <= maxNumOracles,num observations out of bounds)
  //   cfg: transmitter = s_oracles[msg.sender]
  //   cfg: o = s_oracles[signer]
  // OffchainAggregator-transmit-AnswerUpdated: freshness-check, oracle-read
  //   cfg: require(bool,string)(r.hotVars.latestEpochAndRound < epochAndRound,stale report)
  //   cfg: require(bool,string)(_rs.length <= maxNumOracles,too many signatures)
  //   cfg: require(bool,string)(r.observations.length <= maxNumOracles,num observations out of bounds)
  //   cfg: transmitter = s_oracles[msg.sender]
  //   cfg: o = s_oracles[signer]
  // OffchainAggregatorBilling-constructor-LinkTokenSet: oracle-read
  //   cfg: setBillingInternal(_maximumGasPrice,_reasonableGasPrice,_microLinkPerEth,_linkGweiPerObservation,_linkGweiPerTransmission)
  //   cfg: i < maxNumOracles
  //   cfg: s_oracleObservationsCounts = counts
  //   cfg: s_linkToken = _link
  //   cfg: s_gasReimbursementsLinkWei = gas
  // OffchainAggregatorBilling-setLinkToken-LinkTokenSet: oracle-read, oracle-setter, transfer
  //   cfg: payOracles()
  //   cfg: oldLinkToken = s_linkToken
  //   cfg: s_linkToken = _linkToken
  // OffchainAggregatorBilling-setBillingInternal-BillingSet: oracle-read
  //   cfg: s_billing = Billing(_maximumGasPrice,_reasonableGasPrice,_microLinkPerEth,_linkGweiPerObservation,_linkGweiPerTransmission)
  //   cfg: BillingSet(_maximumGasPrice,_reasonableGasPrice,_microLinkPerEth,_linkGweiPerObservation,_linkGweiPerTransmission)
  // OffchainAggregatorBilling-setBillingAccessControllerInternal-BillingAccessControllerSet: 
  //   cfg: oldController = s_billingAccessController
  //   cfg: s_billingAccessController = _billingAccessController
  // OffchainAggregatorBilling-payOracle-OraclePaid: oracle-read, transfer
  //   cfg: oracle = s_oracles[_transmitter]
  //   cfg: s_oracleObservationsCounts[oracle.index] = 1
  //   cfg: s_gasReimbursementsLinkWei[oracle.index] = 1
  //   cfg: OraclePaid(_transmitter,payee,linkWeiAmount,s_linkToken)
  // OffchainAggregatorBilling-payOracles-OraclePaid: oracle-read, transfer
  //   cfg: observationsCounts = s_oracleObservationsCounts
  //   cfg: OraclePaid(transmitters[transmitteridx],payee,linkWeiAmount,linkToken)
  //   cfg: s_oracleObservationsCounts = observationsCounts
  //   cfg: gasReimbursementsLinkWei = s_gasReimbursementsLinkWei
  //   cfg: s_gasReimbursementsLinkWei = gasReimbursementsLinkWei
  // OffchainAggregatorBilling-setPayees-PayeeshipTransferred: transfer
  //   cfg: currentPayee = s_payees[transmitter]
  //   cfg: s_payees[transmitter] = payee
  // OffchainAggregatorBilling-transferPayeeship-PayeeshipTransferRequested: transfer
  //   cfg: previousProposed = s_proposedPayees[_transmitter]
  //   cfg: s_proposedPayees[_transmitter] = _proposed
  // OffchainAggregatorBilling-acceptPayeeship-PayeeshipTransferred: transfer
  //   cfg: require(bool,string)(msg.sender == s_proposedPayees[_transmitter],only proposed payees can accept)
  //   cfg: currentPayee = s_payees[_transmitter]
  //   cfg: s_payees[_transmitter] = msg.sender
  //   cfg: s_proposedPayees[_transmitter] = address(0)
  // Owned-transferOwnership-OwnershipTransferRequested: transfer
  //   cfg: pendingOwner = _to
  // Owned-acceptOwnership-OwnershipTransferred: transfer
  //   cfg: require(bool,string)(msg.sender == pendingOwner,Must be proposed owner)
  //   cfg: oldOwner = owner
  //   cfg: owner = msg.sender
  //   cfg: pendingOwner = address(0)
  //   cfg: OwnershipTransferred(oldOwner,msg.sender)
  // SimpleWriteAccessController-addAccessInternal-AddedAccess: 
  //   cfg: ! accessList[_user]
  //   cfg: accessList[_user] = true
  // SimpleWriteAccessController-removeAccess-RemovedAccess: 
  //   cfg: accessList[_user]
  //   cfg: accessList[_user] = false
  // SimpleWriteAccessController-enableAccessCheck-CheckAccessEnabled: 
  //   cfg: ! checkEnabled
  //   cfg: checkEnabled = true
  // SimpleWriteAccessController-disableAccessCheck-CheckAccessDisabled: 
  //   cfg: checkEnabled
  //   cfg: checkEnabled = false
  // OffchainAggregator-setConfig-ConfigSet: oracle-read, oracle-setter
  //   cfg: payOracle(transmitter)
  //   cfg: delete s_oracles[signer]
  //   cfg: delete s_oracles[transmitter]
  //   cfg: require(bool,string)(s_oracles[_signers[i]].role == Role.Unset,repeated signer address)
  //   cfg: s_oracles[_signers[i]] = Oracle(uint8(i),Role.Signer)
  // OffchainAggregator-setValidatorConfig-ValidatorConfigSet: 
  //   cfg: previous = s_validatorConfig
  //   cfg: s_validatorConfig = ValidatorConfig({validator:_newValidator,gasLimit:_newGasLimit})
  // OffchainAggregator-setRequesterAccessController-RequesterAccessControllerSet: 
  //   cfg: oldController = s_requesterAccessController
  //   cfg: s_requesterAccessController = AccessControllerInterface(_requesterAccessController)
  // OffchainAggregator-requestNewRound-RoundRequested: 
  // OffchainAggregator-transmit-NewTransmission: freshness-check, oracle-read
  //   cfg: require(bool,string)(r.hotVars.latestEpochAndRound < epochAndRound,stale report)
  //   cfg: require(bool,string)(_rs.length <= maxNumOracles,too many signatures)
  //   cfg: require(bool,string)(r.observations.length <= maxNumOracles,num observations out of bounds)
  //   cfg: transmitter = s_oracles[msg.sender]
  //   cfg: o = s_oracles[signer]
  // OffchainAggregator-transmit-NewRound: freshness-check, oracle-read
  //   cfg: require(bool,string)(r.hotVars.latestEpochAndRound < epochAndRound,stale report)
  //   cfg: require(bool,string)(_rs.length <= maxNumOracles,too many signatures)
  //   cfg: require(bool,string)(r.observations.length <= maxNumOracles,num observations out of bounds)
  //   cfg: transmitter = s_oracles[msg.sender]
  //   cfg: o = s_oracles[signer]
  // OffchainAggregator-transmit-AnswerUpdated: freshness-check, oracle-read
  //   cfg: require(bool,string)(r.hotVars.latestEpochAndRound < epochAndRound,stale report)
  //   cfg: require(bool,string)(_rs.length <= maxNumOracles,too many signatures)
  //   cfg: require(bool,string)(r.observations.length <= maxNumOracles,num observations out of bounds)
  //   cfg: transmitter = s_oracles[msg.sender]
  //   cfg: o = s_oracles[signer]
  // OffchainAggregatorBilling-constructor-LinkTokenSet: oracle-read
  //   cfg: setBillingInternal(_maximumGasPrice,_reasonableGasPrice,_microLinkPerEth,_linkGweiPerObservation,_linkGweiPerTransmission)
  //   cfg: i < maxNumOracles
  //   cfg: s_oracleObservationsCounts = counts
  //   cfg: s_linkToken = _link
  //   cfg: s_gasReimbursementsLinkWei = gas
  // OffchainAggregatorBilling-setLinkToken-LinkTokenSet: oracle-read, oracle-setter, transfer
  //   cfg: payOracles()
  //   cfg: oldLinkToken = s_linkToken
  //   cfg: s_linkToken = _linkToken
  // OffchainAggregatorBilling-setBillingInternal-BillingSet: oracle-read
  //   cfg: s_billing = Billing(_maximumGasPrice,_reasonableGasPrice,_microLinkPerEth,_linkGweiPerObservation,_linkGweiPerTransmission)
  //   cfg: BillingSet(_maximumGasPrice,_reasonableGasPrice,_microLinkPerEth,_linkGweiPerObservation,_linkGweiPerTransmission)
  // OffchainAggregatorBilling-setBillingAccessControllerInternal-BillingAccessControllerSet: 
  //   cfg: oldController = s_billingAccessController
  //   cfg: s_billingAccessController = _billingAccessController
  // OffchainAggregatorBilling-payOracle-OraclePaid: oracle-read, transfer
  //   cfg: oracle = s_oracles[_transmitter]
  //   cfg: s_oracleObservationsCounts[oracle.index] = 1
  //   cfg: s_gasReimbursementsLinkWei[oracle.index] = 1
  //   cfg: OraclePaid(_transmitter,payee,linkWeiAmount,s_linkToken)
  // OffchainAggregatorBilling-payOracles-OraclePaid: oracle-read, transfer
  //   cfg: observationsCounts = s_oracleObservationsCounts
  //   cfg: OraclePaid(transmitters[transmitteridx],payee,linkWeiAmount,linkToken)
  //   cfg: s_oracleObservationsCounts = observationsCounts
  //   cfg: gasReimbursementsLinkWei = s_gasReimbursementsLinkWei
  //   cfg: s_gasReimbursementsLinkWei = gasReimbursementsLinkWei
  // OffchainAggregatorBilling-setPayees-PayeeshipTransferred: transfer
  //   cfg: currentPayee = s_payees[transmitter]
  //   cfg: s_payees[transmitter] = payee
  // OffchainAggregatorBilling-transferPayeeship-PayeeshipTransferRequested: transfer
  //   cfg: previousProposed = s_proposedPayees[_transmitter]
  //   cfg: s_proposedPayees[_transmitter] = _proposed
  // OffchainAggregatorBilling-acceptPayeeship-PayeeshipTransferred: transfer
  //   cfg: require(bool,string)(msg.sender == s_proposedPayees[_transmitter],only proposed payees can accept)
  //   cfg: currentPayee = s_payees[_transmitter]
  //   cfg: s_payees[_transmitter] = msg.sender
  //   cfg: s_proposedPayees[_transmitter] = address(0)
  // Owned-transferOwnership-OwnershipTransferRequested: transfer
  //   cfg: pendingOwner = _to
  // Owned-acceptOwnership-OwnershipTransferred: transfer
  //   cfg: require(bool,string)(msg.sender == pendingOwner,Must be proposed owner)
  //   cfg: oldOwner = owner
  //   cfg: owner = msg.sender
  //   cfg: pendingOwner = address(0)
  //   cfg: OwnershipTransferred(oldOwner,msg.sender)
  // SimpleWriteAccessController-addAccessInternal-AddedAccess: 
  //   cfg: ! accessList[_user]
  //   cfg: accessList[_user] = true
  // SimpleWriteAccessController-removeAccess-RemovedAccess: 
  //   cfg: accessList[_user]
  //   cfg: accessList[_user] = false
  // SimpleWriteAccessController-enableAccessCheck-CheckAccessEnabled: 
  //   cfg: ! checkEnabled
  //   cfg: checkEnabled = true
  // SimpleWriteAccessController-disableAccessCheck-CheckAccessDisabled: 
  //   cfg: checkEnabled
  //   cfg: checkEnabled = false
  // OffchainAggregator-setConfig-ConfigSet: oracle-read, oracle-setter
  //   cfg: payOracle(transmitter)
  //   cfg: delete s_oracles[signer]
  //   cfg: delete s_oracles[transmitter]
  //   cfg: require(bool,string)(s_oracles[_signers[i]].role == Role.Unset,repeated signer address)
  //   cfg: s_oracles[_signers[i]] = Oracle(uint8(i),Role.Signer)
  // OffchainAggregator-setValidatorConfig-ValidatorConfigSet: 
  //   cfg: previous = s_validatorConfig
  //   cfg: s_validatorConfig = ValidatorConfig({validator:_newValidator,gasLimit:_newGasLimit})
  // OffchainAggregator-setRequesterAccessController-RequesterAccessControllerSet: 
  //   cfg: oldController = s_requesterAccessController
  //   cfg: s_requesterAccessController = AccessControllerInterface(_requesterAccessController)
  // OffchainAggregator-requestNewRound-RoundRequested: 
  // OffchainAggregator-transmit-NewTransmission: freshness-check, oracle-read
  //   cfg: require(bool,string)(r.hotVars.latestEpochAndRound < epochAndRound,stale report)
  //   cfg: require(bool,string)(_rs.length <= maxNumOracles,too many signatures)
  //   cfg: require(bool,string)(r.observations.length <= maxNumOracles,num observations out of bounds)
  //   cfg: transmitter = s_oracles[msg.sender]
  //   cfg: o = s_oracles[signer]
  // OffchainAggregator-transmit-NewRound: freshness-check, oracle-read
  //   cfg: require(bool,string)(r.hotVars.latestEpochAndRound < epochAndRound,stale report)
  //   cfg: require(bool,string)(_rs.length <= maxNumOracles,too many signatures)
  //   cfg: require(bool,string)(r.observations.length <= maxNumOracles,num observations out of bounds)
  //   cfg: transmitter = s_oracles[msg.sender]
  //   cfg: o = s_oracles[signer]
  // OffchainAggregator-transmit-AnswerUpdated: freshness-check, oracle-read
  //   cfg: require(bool,string)(r.hotVars.latestEpochAndRound < epochAndRound,stale report)
  //   cfg: require(bool,string)(_rs.length <= maxNumOracles,too many signatures)
  //   cfg: require(bool,string)(r.observations.length <= maxNumOracles,num observations out of bounds)
  //   cfg: transmitter = s_oracles[msg.sender]
  //   cfg: o = s_oracles[signer]
  // OffchainAggregatorBilling-constructor-LinkTokenSet: oracle-read
  //   cfg: setBillingInternal(_maximumGasPrice,_reasonableGasPrice,_microLinkPerEth,_linkGweiPerObservation,_linkGweiPerTransmission)
  //   cfg: i < maxNumOracles
  //   cfg: s_oracleObservationsCounts = counts
  //   cfg: s_linkToken = _link
  //   cfg: s_gasReimbursementsLinkWei = gas
  // OffchainAggregatorBilling-setLinkToken-LinkTokenSet: oracle-read, oracle-setter, transfer
  //   cfg: payOracles()
  //   cfg: oldLinkToken = s_linkToken
  //   cfg: s_linkToken = _linkToken
  // OffchainAggregatorBilling-setBillingInternal-BillingSet: oracle-read
  //   cfg: s_billing = Billing(_maximumGasPrice,_reasonableGasPrice,_microLinkPerEth,_linkGweiPerObservation,_linkGweiPerTransmission)
  //   cfg: BillingSet(_maximumGasPrice,_reasonableGasPrice,_microLinkPerEth,_linkGweiPerObservation,_linkGweiPerTransmission)
  // OffchainAggregatorBilling-setBillingAccessControllerInternal-BillingAccessControllerSet: 
  //   cfg: oldController = s_billingAccessController
  //   cfg: s_billingAccessController = _billingAccessController
  // OffchainAggregatorBilling-payOracle-OraclePaid: oracle-read, transfer
  //   cfg: oracle = s_oracles[_transmitter]
  //   cfg: s_oracleObservationsCounts[oracle.index] = 1
  //   cfg: s_gasReimbursementsLinkWei[oracle.index] = 1
  //   cfg: OraclePaid(_transmitter,payee,linkWeiAmount,s_linkToken)
  // OffchainAggregatorBilling-payOracles-OraclePaid: oracle-read, transfer
  //   cfg: observationsCounts = s_oracleObservationsCounts
  //   cfg: OraclePaid(transmitters[transmitteridx],payee,linkWeiAmount,linkToken)
  //   cfg: s_oracleObservationsCounts = observationsCounts
  //   cfg: gasReimbursementsLinkWei = s_gasReimbursementsLinkWei
  //   cfg: s_gasReimbursementsLinkWei = gasReimbursementsLinkWei
  // OffchainAggregatorBilling-setPayees-PayeeshipTransferred: transfer
  //   cfg: currentPayee = s_payees[transmitter]
  //   cfg: s_payees[transmitter] = payee
  // OffchainAggregatorBilling-transferPayeeship-PayeeshipTransferRequested: transfer
  //   cfg: previousProposed = s_proposedPayees[_transmitter]
  //   cfg: s_proposedPayees[_transmitter] = _proposed
  // OffchainAggregatorBilling-acceptPayeeship-PayeeshipTransferred: transfer
  //   cfg: require(bool,string)(msg.sender == s_proposedPayees[_transmitter],only proposed payees can accept)
  //   cfg: currentPayee = s_payees[_transmitter]
  //   cfg: s_payees[_transmitter] = msg.sender
  //   cfg: s_proposedPayees[_transmitter] = address(0)
  // Owned-transferOwnership-OwnershipTransferRequested: transfer
  //   cfg: pendingOwner = _to
  // Owned-acceptOwnership-OwnershipTransferred: transfer
  //   cfg: require(bool,string)(msg.sender == pendingOwner,Must be proposed owner)
  //   cfg: oldOwner = owner
  //   cfg: owner = msg.sender
  //   cfg: pendingOwner = address(0)
  //   cfg: OwnershipTransferred(oldOwner,msg.sender)
  // OffchainAggregator-setConfig-ConfigSet: oracle-read, oracle-setter
  //   cfg: payOracle(transmitter)
  //   cfg: delete s_oracles[signer]
  //   cfg: delete s_oracles[transmitter]
  //   cfg: require(bool,string)(s_oracles[_signers[i]].role == Role.Unset,repeated signer address)
  //   cfg: s_oracles[_signers[i]] = Oracle(uint8(i),Role.Signer)
  // OffchainAggregator-setValidatorConfig-ValidatorConfigSet: 
  //   cfg: previous = s_validatorConfig
  //   cfg: s_validatorConfig = ValidatorConfig({validator:_newValidator,gasLimit:_newGasLimit})
  // OffchainAggregator-setRequesterAccessController-RequesterAccessControllerSet: 
  //   cfg: oldController = s_requesterAccessController
  //   cfg: s_requesterAccessController = AccessControllerInterface(_requesterAccessController)
  // OffchainAggregator-requestNewRound-RoundRequested: 
  // OffchainAggregator-transmit-NewTransmission: freshness-check, oracle-read
  //   cfg: require(bool,string)(r.hotVars.latestEpochAndRound < epochAndRound,stale report)
  //   cfg: require(bool,string)(_rs.length <= maxNumOracles,too many signatures)
  //   cfg: require(bool,string)(r.observations.length <= maxNumOracles,num observations out of bounds)
  //   cfg: transmitter = s_oracles[msg.sender]
  //   cfg: o = s_oracles[signer]
  // OffchainAggregator-transmit-NewRound: freshness-check, oracle-read
  //   cfg: require(bool,string)(r.hotVars.latestEpochAndRound < epochAndRound,stale report)
  //   cfg: require(bool,string)(_rs.length <= maxNumOracles,too many signatures)
  //   cfg: require(bool,string)(r.observations.length <= maxNumOracles,num observations out of bounds)
  //   cfg: transmitter = s_oracles[msg.sender]
  //   cfg: o = s_oracles[signer]
  // OffchainAggregator-transmit-AnswerUpdated: freshness-check, oracle-read
  //   cfg: require(bool,string)(r.hotVars.latestEpochAndRound < epochAndRound,stale report)
  //   cfg: require(bool,string)(_rs.length <= maxNumOracles,too many signatures)
  //   cfg: require(bool,string)(r.observations.length <= maxNumOracles,num observations out of bounds)
  //   cfg: transmitter = s_oracles[msg.sender]
  //   cfg: o = s_oracles[signer]
  // OffchainAggregatorBilling-constructor-LinkTokenSet: oracle-read
  //   cfg: setBillingInternal(_maximumGasPrice,_reasonableGasPrice,_microLinkPerEth,_linkGweiPerObservation,_linkGweiPerTransmission)
  //   cfg: i < maxNumOracles
  //   cfg: s_oracleObservationsCounts = counts
  //   cfg: s_linkToken = _link
  //   cfg: s_gasReimbursementsLinkWei = gas
  // OffchainAggregatorBilling-setLinkToken-LinkTokenSet: oracle-read, oracle-setter, transfer
  //   cfg: payOracles()
  //   cfg: oldLinkToken = s_linkToken
  //   cfg: s_linkToken = _linkToken
  // OffchainAggregatorBilling-setBillingInternal-BillingSet: oracle-read
  //   cfg: s_billing = Billing(_maximumGasPrice,_reasonableGasPrice,_microLinkPerEth,_linkGweiPerObservation,_linkGweiPerTransmission)
  //   cfg: BillingSet(_maximumGasPrice,_reasonableGasPrice,_microLinkPerEth,_linkGweiPerObservation,_linkGweiPerTransmission)
  // OffchainAggregatorBilling-setBillingAccessControllerInternal-BillingAccessControllerSet: 
  //   cfg: oldController = s_billingAccessController
  //   cfg: s_billingAccessController = _billingAccessController
  // OffchainAggregatorBilling-payOracle-OraclePaid: oracle-read, transfer
  //   cfg: oracle = s_oracles[_transmitter]
  //   cfg: s_oracleObservationsCounts[oracle.index] = 1
  //   cfg: s_gasReimbursementsLinkWei[oracle.index] = 1
  //   cfg: OraclePaid(_transmitter,payee,linkWeiAmount,s_linkToken)
  // OffchainAggregatorBilling-payOracles-OraclePaid: oracle-read, transfer
  //   cfg: observationsCounts = s_oracleObservationsCounts
  //   cfg: OraclePaid(transmitters[transmitteridx],payee,linkWeiAmount,linkToken)
  //   cfg: s_oracleObservationsCounts = observationsCounts
  //   cfg: gasReimbursementsLinkWei = s_gasReimbursementsLinkWei
  //   cfg: s_gasReimbursementsLinkWei = gasReimbursementsLinkWei
  // OffchainAggregatorBilling-setPayees-PayeeshipTransferred: transfer
  //   cfg: currentPayee = s_payees[transmitter]
  //   cfg: s_payees[transmitter] = payee
  // OffchainAggregatorBilling-transferPayeeship-PayeeshipTransferRequested: transfer
  //   cfg: previousProposed = s_proposedPayees[_transmitter]
  //   cfg: s_proposedPayees[_transmitter] = _proposed
  // OffchainAggregatorBilling-acceptPayeeship-PayeeshipTransferred: transfer
  //   cfg: require(bool,string)(msg.sender == s_proposedPayees[_transmitter],only proposed payees can accept)
  //   cfg: currentPayee = s_payees[_transmitter]
  //   cfg: s_payees[_transmitter] = msg.sender
  //   cfg: s_proposedPayees[_transmitter] = address(0)
  // Owned-transferOwnership-OwnershipTransferRequested: transfer
  //   cfg: pendingOwner = _to
  // Owned-acceptOwnership-OwnershipTransferred: transfer
  //   cfg: require(bool,string)(msg.sender == pendingOwner,Must be proposed owner)
  //   cfg: oldOwner = owner
  //   cfg: owner = msg.sender
  //   cfg: pendingOwner = address(0)
  //   cfg: OwnershipTransferred(oldOwner,msg.sender)
  // OffchainAggregatorBilling-constructor-LinkTokenSet: oracle-read
  //   cfg: setBillingInternal(_maximumGasPrice,_reasonableGasPrice,_microLinkPerEth,_linkGweiPerObservation,_linkGweiPerTransmission)
  //   cfg: i < maxNumOracles
  //   cfg: s_oracleObservationsCounts = counts
  //   cfg: s_linkToken = _link
  //   cfg: s_gasReimbursementsLinkWei = gas
  // OffchainAggregatorBilling-setLinkToken-LinkTokenSet: oracle-read, oracle-setter, transfer
  //   cfg: payOracles()
  //   cfg: oldLinkToken = s_linkToken
  //   cfg: s_linkToken = _linkToken
  // OffchainAggregatorBilling-setBillingInternal-BillingSet: oracle-read
  //   cfg: s_billing = Billing(_maximumGasPrice,_reasonableGasPrice,_microLinkPerEth,_linkGweiPerObservation,_linkGweiPerTransmission)
  //   cfg: BillingSet(_maximumGasPrice,_reasonableGasPrice,_microLinkPerEth,_linkGweiPerObservation,_linkGweiPerTransmission)
  // OffchainAggregatorBilling-setBillingAccessControllerInternal-BillingAccessControllerSet: 
  //   cfg: oldController = s_billingAccessController
  //   cfg: s_billingAccessController = _billingAccessController
  // OffchainAggregatorBilling-payOracle-OraclePaid: oracle-read, transfer
  //   cfg: oracle = s_oracles[_transmitter]
  //   cfg: s_oracleObservationsCounts[oracle.index] = 1
  //   cfg: s_gasReimbursementsLinkWei[oracle.index] = 1
  //   cfg: OraclePaid(_transmitter,payee,linkWeiAmount,s_linkToken)
  // OffchainAggregatorBilling-payOracles-OraclePaid: oracle-read, transfer
  //   cfg: observationsCounts = s_oracleObservationsCounts
  //   cfg: OraclePaid(transmitters[transmitteridx],payee,linkWeiAmount,linkToken)
  //   cfg: s_oracleObservationsCounts = observationsCounts
  //   cfg: gasReimbursementsLinkWei = s_gasReimbursementsLinkWei
  //   cfg: s_gasReimbursementsLinkWei = gasReimbursementsLinkWei
  // OffchainAggregatorBilling-setPayees-PayeeshipTransferred: transfer
  //   cfg: currentPayee = s_payees[transmitter]
  //   cfg: s_payees[transmitter] = payee
  // OffchainAggregatorBilling-transferPayeeship-PayeeshipTransferRequested: transfer
  //   cfg: previousProposed = s_proposedPayees[_transmitter]
  //   cfg: s_proposedPayees[_transmitter] = _proposed
  // OffchainAggregatorBilling-acceptPayeeship-PayeeshipTransferred: transfer
  //   cfg: require(bool,string)(msg.sender == s_proposedPayees[_transmitter],only proposed payees can accept)
  //   cfg: currentPayee = s_payees[_transmitter]
  //   cfg: s_payees[_transmitter] = msg.sender
  //   cfg: s_proposedPayees[_transmitter] = address(0)
  // Owned-transferOwnership-OwnershipTransferRequested: transfer
  //   cfg: pendingOwner = _to
  // Owned-acceptOwnership-OwnershipTransferred: transfer
  //   cfg: require(bool,string)(msg.sender == pendingOwner,Must be proposed owner)
  //   cfg: oldOwner = owner
  //   cfg: owner = msg.sender
  //   cfg: pendingOwner = address(0)
  //   cfg: OwnershipTransferred(oldOwner,msg.sender)
  // Owned-transferOwnership-OwnershipTransferRequested: transfer
  //   cfg: pendingOwner = _to
  // Owned-acceptOwnership-OwnershipTransferred: transfer
  //   cfg: require(bool,string)(msg.sender == pendingOwner,Must be proposed owner)
  //   cfg: oldOwner = owner
  //   cfg: owner = msg.sender
  //   cfg: pendingOwner = address(0)
  //   cfg: OwnershipTransferred(oldOwner,msg.sender)
  // Owned-transferOwnership-OwnershipTransferRequested: transfer
  //   cfg: pendingOwner = _to
  // Owned-acceptOwnership-OwnershipTransferred: transfer
  //   cfg: require(bool,string)(msg.sender == pendingOwner,Must be proposed owner)
  //   cfg: oldOwner = owner
  //   cfg: owner = msg.sender
  //   cfg: pendingOwner = address(0)
  //   cfg: OwnershipTransferred(oldOwner,msg.sender)
  // SimpleWriteAccessController-addAccessInternal-AddedAccess: 
  //   cfg: ! accessList[_user]
  //   cfg: accessList[_user] = true
  // SimpleWriteAccessController-removeAccess-RemovedAccess: 
  //   cfg: accessList[_user]
  //   cfg: accessList[_user] = false
  // SimpleWriteAccessController-enableAccessCheck-CheckAccessEnabled: 
  //   cfg: ! checkEnabled
  //   cfg: checkEnabled = true
  // SimpleWriteAccessController-disableAccessCheck-CheckAccessDisabled: 
  //   cfg: checkEnabled
  //   cfg: checkEnabled = false
  // Owned-transferOwnership-OwnershipTransferRequested: transfer
  //   cfg: pendingOwner = _to
  // Owned-acceptOwnership-OwnershipTransferred: transfer
  //   cfg: require(bool,string)(msg.sender == pendingOwner,Must be proposed owner)
  //   cfg: oldOwner = owner
  //   cfg: owner = msg.sender
  //   cfg: pendingOwner = address(0)
  //   cfg: OwnershipTransferred(oldOwner,msg.sender)
  // SimpleWriteAccessController-addAccessInternal-AddedAccess: 
  //   cfg: ! accessList[_user]
  //   cfg: accessList[_user] = true
  // SimpleWriteAccessController-removeAccess-RemovedAccess: 
  //   cfg: accessList[_user]
  //   cfg: accessList[_user] = false
  // SimpleWriteAccessController-enableAccessCheck-CheckAccessEnabled: 
  //   cfg: ! checkEnabled
  //   cfg: checkEnabled = true
  // SimpleWriteAccessController-disableAccessCheck-CheckAccessDisabled: 
  //   cfg: checkEnabled
  //   cfg: checkEnabled = false
  // AccessControlTestHelper-readGetRoundData-Dummy: 
  // AccessControlTestHelper-readLatestRoundData-Dummy: oracle-read
  //   cfg: AccessControlledOffchainAggregator(_aggregator).latestRoundData()
  // AccessControlTestHelper-readLatestAnswer-Dummy: oracle-read
  //   cfg: AccessControlledOffchainAggregator(_aggregator).latestAnswer()
  // AccessControlTestHelper-readLatestTimestamp-Dummy: 
  // AccessControlTestHelper-readLatestRound-Dummy: 
  // AccessControlTestHelper-readGetAnswer-Dummy: 
  // AccessControlTestHelper-readGetTimestamp-Dummy: 
  // OffchainAggregator-setConfig-ConfigSet: oracle-read, oracle-setter
  //   cfg: payOracle(transmitter)
  //   cfg: delete s_oracles[signer]
  //   cfg: delete s_oracles[transmitter]
  //   cfg: require(bool,string)(s_oracles[_signers[i]].role == Role.Unset,repeated signer address)
  //   cfg: s_oracles[_signers[i]] = Oracle(uint8(i),Role.Signer)
  // OffchainAggregator-setValidatorConfig-ValidatorConfigSet: 
  //   cfg: previous = s_validatorConfig
  //   cfg: s_validatorConfig = ValidatorConfig({validator:_newValidator,gasLimit:_newGasLimit})
  // OffchainAggregator-setRequesterAccessController-RequesterAccessControllerSet: 
  //   cfg: oldController = s_requesterAccessController
  //   cfg: s_requesterAccessController = AccessControllerInterface(_requesterAccessController)
  // OffchainAggregator-requestNewRound-RoundRequested: 
  // OffchainAggregator-transmit-NewTransmission: freshness-check, oracle-read
  //   cfg: require(bool,string)(r.hotVars.latestEpochAndRound < epochAndRound,stale report)
  //   cfg: require(bool,string)(_rs.length <= maxNumOracles,too many signatures)
  //   cfg: require(bool,string)(r.observations.length <= maxNumOracles,num observations out of bounds)
  //   cfg: transmitter = s_oracles[msg.sender]
  //   cfg: o = s_oracles[signer]
  // OffchainAggregator-transmit-NewRound: freshness-check, oracle-read
  //   cfg: require(bool,string)(r.hotVars.latestEpochAndRound < epochAndRound,stale report)
  //   cfg: require(bool,string)(_rs.length <= maxNumOracles,too many signatures)
  //   cfg: require(bool,string)(r.observations.length <= maxNumOracles,num observations out of bounds)
  //   cfg: transmitter = s_oracles[msg.sender]
  //   cfg: o = s_oracles[signer]
  // OffchainAggregator-transmit-AnswerUpdated: freshness-check, oracle-read
  //   cfg: require(bool,string)(r.hotVars.latestEpochAndRound < epochAndRound,stale report)
  //   cfg: require(bool,string)(_rs.length <= maxNumOracles,too many signatures)
  //   cfg: require(bool,string)(r.observations.length <= maxNumOracles,num observations out of bounds)
  //   cfg: transmitter = s_oracles[msg.sender]
  //   cfg: o = s_oracles[signer]
  // OffchainAggregatorBilling-constructor-LinkTokenSet: oracle-read
  //   cfg: setBillingInternal(_maximumGasPrice,_reasonableGasPrice,_microLinkPerEth,_linkGweiPerObservation,_linkGweiPerTransmission)
  //   cfg: i < maxNumOracles
  //   cfg: s_oracleObservationsCounts = counts
  //   cfg: s_linkToken = _link
  //   cfg: s_gasReimbursementsLinkWei = gas
  // OffchainAggregatorBilling-setLinkToken-LinkTokenSet: oracle-read, oracle-setter, transfer
  //   cfg: payOracles()
  //   cfg: oldLinkToken = s_linkToken
  //   cfg: s_linkToken = _linkToken
  // OffchainAggregatorBilling-setBillingInternal-BillingSet: oracle-read
  //   cfg: s_billing = Billing(_maximumGasPrice,_reasonableGasPrice,_microLinkPerEth,_linkGweiPerObservation,_linkGweiPerTransmission)
  //   cfg: BillingSet(_maximumGasPrice,_reasonableGasPrice,_microLinkPerEth,_linkGweiPerObservation,_linkGweiPerTransmission)
  // OffchainAggregatorBilling-setBillingAccessControllerInternal-BillingAccessControllerSet: 
  //   cfg: oldController = s_billingAccessController
  //   cfg: s_billingAccessController = _billingAccessController
  // OffchainAggregatorBilling-payOracle-OraclePaid: oracle-read, transfer
  //   cfg: oracle = s_oracles[_transmitter]
  //   cfg: s_oracleObservationsCounts[oracle.index] = 1
  //   cfg: s_gasReimbursementsLinkWei[oracle.index] = 1
  //   cfg: OraclePaid(_transmitter,payee,linkWeiAmount,s_linkToken)
  // OffchainAggregatorBilling-payOracles-OraclePaid: oracle-read, transfer
  //   cfg: observationsCounts = s_oracleObservationsCounts
  //   cfg: OraclePaid(transmitters[transmitteridx],payee,linkWeiAmount,linkToken)
  //   cfg: s_oracleObservationsCounts = observationsCounts
  //   cfg: gasReimbursementsLinkWei = s_gasReimbursementsLinkWei
  //   cfg: s_gasReimbursementsLinkWei = gasReimbursementsLinkWei
  // OffchainAggregatorBilling-setPayees-PayeeshipTransferred: transfer
  //   cfg: currentPayee = s_payees[transmitter]
  //   cfg: s_payees[transmitter] = payee
  // OffchainAggregatorBilling-transferPayeeship-PayeeshipTransferRequested: transfer
  //   cfg: previousProposed = s_proposedPayees[_transmitter]
  //   cfg: s_proposedPayees[_transmitter] = _proposed
  // OffchainAggregatorBilling-acceptPayeeship-PayeeshipTransferred: transfer
  //   cfg: require(bool,string)(msg.sender == s_proposedPayees[_transmitter],only proposed payees can accept)
  //   cfg: currentPayee = s_payees[_transmitter]
  //   cfg: s_payees[_transmitter] = msg.sender
  //   cfg: s_proposedPayees[_transmitter] = address(0)
  // Owned-transferOwnership-OwnershipTransferRequested: transfer
  //   cfg: pendingOwner = _to
  // Owned-acceptOwnership-OwnershipTransferred: transfer
  //   cfg: require(bool,string)(msg.sender == pendingOwner,Must be proposed owner)
  //   cfg: oldOwner = owner
  //   cfg: owner = msg.sender
  //   cfg: pendingOwner = address(0)
  //   cfg: OwnershipTransferred(oldOwner,msg.sender)
  // SimpleWriteAccessController-addAccessInternal-AddedAccess: 
  //   cfg: ! accessList[_user]
  //   cfg: accessList[_user] = true
  // SimpleWriteAccessController-removeAccess-RemovedAccess: 
  //   cfg: accessList[_user]
  //   cfg: accessList[_user] = false
  // SimpleWriteAccessController-enableAccessCheck-CheckAccessEnabled: 
  //   cfg: ! checkEnabled
  //   cfg: checkEnabled = true
  // SimpleWriteAccessController-disableAccessCheck-CheckAccessDisabled: 
  //   cfg: checkEnabled
  //   cfg: checkEnabled = false
  // TestValidator-validate-Validated: 
  //   cfg: s_latestRoundId = currentRoundId
endmodule
