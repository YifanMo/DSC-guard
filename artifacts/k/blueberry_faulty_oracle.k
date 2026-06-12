requires "domains.md"

module DSC-GUARD-BLUEBERRY-FAULTY-ORACLE-SYNTAX
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

module DSC-GUARD-BLUEBERRY-FAULTY-ORACLE
  imports DSC-GUARD-BLUEBERRY-FAULTY-ORACLE-SYNTAX
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
  // constraint BLUEBERRY_MONEY_MARKET_MUST_USE_NORMALIZED_ORACLE_SEMANTICS: type=decimal_semantics_mismatch severity=critical

  // Slither-mined event semantics.
  // Ownable2StepUpgradeable-transferOwnership-OwnershipTransferStarted: transfer
  //   cfg: _pendingOwner = newOwner
  // OwnableUpgradeable-transferOwnership-OwnershipTransferred: transfer
  //   cfg: oldOwner = _owner
  //   cfg: _owner = newOwner
  // Initializable-disableInitializers-Initialized: 
  //   cfg: _initialized != type()(uint8).max
  //   cfg: _initialized = type()(uint8).max
  // OwnableUpgradeable-transferOwnership-OwnershipTransferred: transfer
  //   cfg: oldOwner = _owner
  //   cfg: _owner = newOwner
  // Initializable-disableInitializers-Initialized: 
  //   cfg: _initialized != type()(uint8).max
  //   cfg: _initialized = type()(uint8).max
  // Initializable-disableInitializers-Initialized: 
  //   cfg: _initialized != type()(uint8).max
  //   cfg: _initialized = type()(uint8).max
  // Initializable-disableInitializers-Initialized: 
  //   cfg: _initialized != type()(uint8).max
  //   cfg: _initialized = type()(uint8).max
  // Ownable2StepUpgradeable-transferOwnership-OwnershipTransferStarted: transfer
  //   cfg: _pendingOwner = newOwner
  // OwnableUpgradeable-transferOwnership-OwnershipTransferred: transfer
  //   cfg: oldOwner = _owner
  //   cfg: _owner = newOwner
  // Initializable-disableInitializers-Initialized: 
  //   cfg: _initialized != type()(uint8).max
  //   cfg: _initialized = type()(uint8).max
  // OwnableUpgradeable-transferOwnership-OwnershipTransferred: transfer
  //   cfg: oldOwner = _owner
  //   cfg: _owner = newOwner
  // Initializable-disableInitializers-Initialized: 
  //   cfg: _initialized != type()(uint8).max
  //   cfg: _initialized = type()(uint8).max
  // Initializable-disableInitializers-Initialized: 
  //   cfg: _initialized != type()(uint8).max
  //   cfg: _initialized = type()(uint8).max
  // Initializable-disableInitializers-Initialized: 
  //   cfg: _initialized != type()(uint8).max
  //   cfg: _initialized = type()(uint8).max
  // PausableUpgradeable-pause-Paused: pause
  //   cfg: _paused = true
  // PausableUpgradeable-unpause-Unpaused: pause
  //   cfg: _paused = false
  // Initializable-disableInitializers-Initialized: 
  //   cfg: _initialized != type()(uint8).max
  //   cfg: _initialized = type()(uint8).max
  // Ownable-transferOwnership-OwnershipTransferred: transfer
  //   cfg: oldOwner = _owner
  //   cfg: _owner = newOwner
  // ERC1967Utils-upgradeToAndCall-Upgraded: 
  // ERC1967Utils-changeAdmin-AdminChanged: 
  // ERC1967Utils-upgradeBeaconToAndCall-BeaconUpgraded: 
  // ERC1967Utils-upgradeToAndCall-Upgraded: 
  // ERC1967Utils-changeAdmin-AdminChanged: 
  // ERC1967Utils-upgradeBeaconToAndCall-BeaconUpgraded: 
  // Ownable-transferOwnership-OwnershipTransferred: transfer
  //   cfg: oldOwner = _owner
  //   cfg: _owner = newOwner
  // ERC1967Utils-upgradeToAndCall-Upgraded: 
  // ERC1967Utils-changeAdmin-AdminChanged: 
  // ERC1967Utils-upgradeBeaconToAndCall-BeaconUpgraded: 
  // Ownable-transferOwnership-OwnershipTransferred: transfer
  //   cfg: oldOwner = _owner
  //   cfg: _owner = newOwner
  // ERC1967Utils-upgradeToAndCall-Upgraded: 
  // ERC1967Utils-changeAdmin-AdminChanged: 
  // ERC1967Utils-upgradeBeaconToAndCall-BeaconUpgraded: 
  // Ownable-transferOwnership-OwnershipTransferred: transfer
  //   cfg: oldOwner = _owner
  //   cfg: _owner = newOwner
  // ERC1967Utils-upgradeToAndCall-Upgraded: 
  // ERC1967Utils-changeAdmin-AdminChanged: 
  // ERC1967Utils-upgradeBeaconToAndCall-BeaconUpgraded: 
  // ERC1967Utils-upgradeToAndCall-Upgraded: 
  // ERC1967Utils-changeAdmin-AdminChanged: 
  // ERC1967Utils-upgradeBeaconToAndCall-BeaconUpgraded: 
  // Ownable-transferOwnership-OwnershipTransferred: transfer
  //   cfg: oldOwner = _owner
  //   cfg: _owner = newOwner
  // ERC1967Utils-upgradeToAndCall-Upgraded: 
  // ERC1967Utils-changeAdmin-AdminChanged: 
  // ERC1967Utils-upgradeBeaconToAndCall-BeaconUpgraded: 
  // Ownable-transferOwnership-OwnershipTransferred: transfer
  //   cfg: oldOwner = _owner
  //   cfg: _owner = newOwner
  // ERC1967Utils-upgradeToAndCall-Upgraded: 
  // ERC1967Utils-changeAdmin-AdminChanged: 
  // ERC1967Utils-upgradeBeaconToAndCall-BeaconUpgraded: 
  // BToken-approve-Approval: transfer
  //   cfg: transferAllowances[src][spender] = amount
  // BToken-accrueInterest-AccrueInterest: borrow
  //   cfg: accrualBlockTimestampPrior = accrualBlockTimestamp
  //   cfg: accrualBlockTimestampPrior == currentBlockTimestamp
  //   cfg: borrowsPrior = totalBorrows
  //   cfg: reservesPrior = totalReserves
  //   cfg: borrowIndexPrior = borrowIndex
  // BToken-borrowFresh-Borrow: borrow, freshness-check, transfer
  //   cfg: require(bool,string)(accrualBlockTimestamp == getBlockTimestamp(),market is stale)
  //   cfg: vars.accountBorrows = borrowBalanceStoredInternal(borrower)
  //   cfg: vars.accountBorrowsNew = add_(vars.accountBorrows,borrowAmount)
  //   cfg: vars.totalBorrowsNew = add_(totalBorrows,borrowAmount)
  //   cfg: accountBorrows[borrower].principal = vars.accountBorrowsNew
  // BToken-repayBorrowFresh-RepayBorrow: borrow, freshness-check, transfer
  //   cfg: require(bool,string)(accrualBlockTimestamp == getBlockTimestamp(),market is stale)
  //   cfg: vars.borrowerIndex = accountBorrows[borrower].interestIndex
  //   cfg: vars.accountBorrows = borrowBalanceStoredInternal(borrower)
  //   cfg: vars.repayAmount = vars.accountBorrows
  //   cfg: vars.accountBorrowsNew = sub_(vars.accountBorrows,vars.actualRepayAmount)
  // BToken-liquidateBorrowFresh-LiquidateBorrow: borrow, freshness-check, liquidate
  //   cfg: require(bool,string)(accrualBlockTimestamp == getBlockTimestamp(),market is stale)
  //   cfg: require(bool,string)(bTokenCollateral.accrualBlockTimestamp() == getBlockTimestamp(),market is stale)
  // BToken-setPendingAdmin-NewPendingAdmin: 
  //   cfg: oldPendingAdmin = pendingAdmin
  //   cfg: pendingAdmin = newPendingAdmin
  //   cfg: NewPendingAdmin(oldPendingAdmin,newPendingAdmin)
  // BToken-acceptAdmin-NewAdmin: 
  //   cfg: msg.sender != pendingAdmin || msg.sender == address(0)
  //   cfg: fail(Error.UNAUTHORIZED,FailureInfo.ACCEPT_ADMIN_PENDING_ADMIN_CHECK)
  //   cfg: oldAdmin = admin
  //   cfg: oldPendingAdmin = pendingAdmin
  //   cfg: admin = pendingAdmin
  // BToken-acceptAdmin-NewPendingAdmin: 
  //   cfg: msg.sender != pendingAdmin || msg.sender == address(0)
  //   cfg: fail(Error.UNAUTHORIZED,FailureInfo.ACCEPT_ADMIN_PENDING_ADMIN_CHECK)
  //   cfg: oldAdmin = admin
  //   cfg: oldPendingAdmin = pendingAdmin
  //   cfg: admin = pendingAdmin
  // BToken-setComptroller-NewComptroller: 
  //   cfg: fail(Error.UNAUTHORIZED,FailureInfo.SET_COMPTROLLER_OWNER_CHECK)
  //   cfg: oldComptroller = comptroller
  //   cfg: require(bool,string)(newComptroller.isComptroller(),not comptroller)
  //   cfg: comptroller = newComptroller
  //   cfg: NewComptroller(oldComptroller,newComptroller)
  // BToken-setReserveFactorFresh-NewReserveFactor: 
  //   cfg: newReserveFactorMantissa > reserveFactorMaxMantissa
  //   cfg: oldReserveFactorMantissa = reserveFactorMantissa
  //   cfg: reserveFactorMantissa = newReserveFactorMantissa
  //   cfg: NewReserveFactor(oldReserveFactorMantissa,newReserveFactorMantissa)
  // BToken-addReservesFresh-ReservesAdded: transfer
  //   cfg: totalReservesNew = add_(totalReserves,actualAddAmount)
  //   cfg: totalReserves = totalReservesNew
  //   cfg: ReservesAdded(msg.sender,actualAddAmount,totalReservesNew)
  // BToken-reduceReservesFresh-ReservesReduced: transfer
  //   cfg: reduceAmount > totalReserves
  //   cfg: totalReservesNew = sub_(totalReserves,reduceAmount)
  //   cfg: totalReserves = totalReservesNew
  //   cfg: ReservesReduced(admin,reduceAmount,totalReservesNew)
  // BToken-setInterestRateModelFresh-NewMarketInterestRateModel: 
  //   cfg: oldInterestRateModel = interestRateModel
  //   cfg: require(bool,string)(newInterestRateModel.isInterestRateModel(),invalid IRM)
  //   cfg: interestRateModel = newInterestRateModel
  //   cfg: NewMarketInterestRateModel(oldInterestRateModel,newInterestRateModel)
  // ComptrollerErrorReporter-fail-Failure: 
  // ComptrollerErrorReporter-failOpaque-Failure: 
  // TokenErrorReporter-fail-Failure: 
  // TokenErrorReporter-failOpaque-Failure: 
  // BToken-approve-Approval: transfer
  //   cfg: transferAllowances[src][spender] = amount
  // BToken-accrueInterest-AccrueInterest: borrow
  //   cfg: accrualBlockTimestampPrior = accrualBlockTimestamp
  //   cfg: accrualBlockTimestampPrior == currentBlockTimestamp
  //   cfg: borrowsPrior = totalBorrows
  //   cfg: reservesPrior = totalReserves
  //   cfg: borrowIndexPrior = borrowIndex
  // BToken-borrowFresh-Borrow: borrow, freshness-check, transfer
  //   cfg: require(bool,string)(accrualBlockTimestamp == getBlockTimestamp(),market is stale)
  //   cfg: vars.accountBorrows = borrowBalanceStoredInternal(borrower)
  //   cfg: vars.accountBorrowsNew = add_(vars.accountBorrows,borrowAmount)
  //   cfg: vars.totalBorrowsNew = add_(totalBorrows,borrowAmount)
  //   cfg: accountBorrows[borrower].principal = vars.accountBorrowsNew
  // BToken-repayBorrowFresh-RepayBorrow: borrow, freshness-check, transfer
  //   cfg: require(bool,string)(accrualBlockTimestamp == getBlockTimestamp(),market is stale)
  //   cfg: vars.borrowerIndex = accountBorrows[borrower].interestIndex
  //   cfg: vars.accountBorrows = borrowBalanceStoredInternal(borrower)
  //   cfg: vars.repayAmount = vars.accountBorrows
  //   cfg: vars.accountBorrowsNew = sub_(vars.accountBorrows,vars.actualRepayAmount)
  // BToken-liquidateBorrowFresh-LiquidateBorrow: borrow, freshness-check, liquidate
  //   cfg: require(bool,string)(accrualBlockTimestamp == getBlockTimestamp(),market is stale)
  //   cfg: require(bool,string)(bTokenCollateral.accrualBlockTimestamp() == getBlockTimestamp(),market is stale)
  // BToken-setPendingAdmin-NewPendingAdmin: 
  //   cfg: oldPendingAdmin = pendingAdmin
  //   cfg: pendingAdmin = newPendingAdmin
  //   cfg: NewPendingAdmin(oldPendingAdmin,newPendingAdmin)
  // BToken-acceptAdmin-NewAdmin: 
  //   cfg: msg.sender != pendingAdmin || msg.sender == address(0)
  //   cfg: fail(Error.UNAUTHORIZED,FailureInfo.ACCEPT_ADMIN_PENDING_ADMIN_CHECK)
  //   cfg: oldAdmin = admin
  //   cfg: oldPendingAdmin = pendingAdmin
  //   cfg: admin = pendingAdmin
  // BToken-acceptAdmin-NewPendingAdmin: 
  //   cfg: msg.sender != pendingAdmin || msg.sender == address(0)
  //   cfg: fail(Error.UNAUTHORIZED,FailureInfo.ACCEPT_ADMIN_PENDING_ADMIN_CHECK)
  //   cfg: oldAdmin = admin
  //   cfg: oldPendingAdmin = pendingAdmin
  //   cfg: admin = pendingAdmin
  // BToken-setComptroller-NewComptroller: 
  //   cfg: fail(Error.UNAUTHORIZED,FailureInfo.SET_COMPTROLLER_OWNER_CHECK)
  //   cfg: oldComptroller = comptroller
  //   cfg: require(bool,string)(newComptroller.isComptroller(),not comptroller)
  //   cfg: comptroller = newComptroller
  //   cfg: NewComptroller(oldComptroller,newComptroller)
  // BToken-setReserveFactorFresh-NewReserveFactor: 
  //   cfg: newReserveFactorMantissa > reserveFactorMaxMantissa
  //   cfg: oldReserveFactorMantissa = reserveFactorMantissa
  //   cfg: reserveFactorMantissa = newReserveFactorMantissa
  //   cfg: NewReserveFactor(oldReserveFactorMantissa,newReserveFactorMantissa)
  // BToken-addReservesFresh-ReservesAdded: transfer
  //   cfg: totalReservesNew = add_(totalReserves,actualAddAmount)
  //   cfg: totalReserves = totalReservesNew
  //   cfg: ReservesAdded(msg.sender,actualAddAmount,totalReservesNew)
  // BToken-reduceReservesFresh-ReservesReduced: transfer
  //   cfg: reduceAmount > totalReserves
  //   cfg: totalReservesNew = sub_(totalReserves,reduceAmount)
  //   cfg: totalReserves = totalReservesNew
  //   cfg: ReservesReduced(admin,reduceAmount,totalReservesNew)
  // BToken-setInterestRateModelFresh-NewMarketInterestRateModel: 
  //   cfg: oldInterestRateModel = interestRateModel
  //   cfg: require(bool,string)(newInterestRateModel.isInterestRateModel(),invalid IRM)
  //   cfg: interestRateModel = newInterestRateModel
  //   cfg: NewMarketInterestRateModel(oldInterestRateModel,newInterestRateModel)
  // Comptroller-addToMarketInternal-MarketEntered: borrow
  //   cfg: marketToJoin = markets[address(bToken)]
  //   cfg: accountAssets[borrower].push(bToken)
  // Comptroller-exitMarket-MarketExited: borrow, redeem
  // Comptroller-updateBTokenVersion-NewBTokenVersion: 
  //   cfg: oldVersion = markets[bToken].version
  //   cfg: markets[bToken].version = newVersion
  // Comptroller-setPriceOracle-NewPriceOracle: oracle-read, oracle-setter
  //   cfg: fail(Error.UNAUTHORIZED,FailureInfo.SET_PRICE_ORACLE_OWNER_CHECK)
  //   cfg: oldOracle = oracle
  //   cfg: oracle = newOracle
  //   cfg: NewPriceOracle(oldOracle,newOracle)
  // Comptroller-setCloseFactor-NewCloseFactor: 
  //   cfg: oldCloseFactorMantissa = closeFactorMantissa
  //   cfg: closeFactorMantissa = newCloseFactorMantissa
  //   cfg: NewCloseFactor(oldCloseFactorMantissa,closeFactorMantissa)
  // Comptroller-setCollateralFactor-NewCollateralFactor: oracle-read, oracle-setter
  //   cfg: newCollateralFactorMantissa != 0 && oracle.getUnderlyingPrice(bToken) == 0
  //   cfg: fail(Error.PRICE_ERROR,FailureInfo.SET_COLLATERAL_FACTOR_WITHOUT_PRICE)
  //   cfg: market = markets[address(bToken)]
  // Comptroller-setLiquidationIncentive-NewLiquidationIncentive: 
  //   cfg: oldLiquidationIncentiveMantissa = liquidationIncentiveMantissa
  //   cfg: liquidationIncentiveMantissa = newLiquidationIncentiveMantissa
  //   cfg: NewLiquidationIncentive(oldLiquidationIncentiveMantissa,newLiquidationIncentiveMantissa)
  // Comptroller-supportMarket-MarketListed: 
  //   cfg: markets[address(bToken)] = Market({isListed:true,collateralFactorMantissa:0,version:version})
  // Comptroller-delistMarket-MarketDelisted: borrow, mint, pause
  //   cfg: require(bool,string)(markets[address(bToken)].collateralFactorMantissa == 0,market has collateral)
  //   cfg: isMarketDelisted[address(bToken)] = true
  //   cfg: delete markets[address(bToken)]
  //   cfg: i < allMarkets.length
  //   cfg: allMarkets[i] == bToken
  // Comptroller-setMarketSupplyCaps-NewSupplyCap: supply
  //   cfg: numSupplyCaps = newSupplyCaps.length
  //   cfg: require(bool,string)(numMarkets != 0 && numMarkets == numSupplyCaps,invalid input)
  //   cfg: supplyCaps[address(bTokens[i])] = newSupplyCaps[i]
  //   cfg: NewSupplyCap(bTokens[i],newSupplyCaps[i])
  // Comptroller-setMarketBorrowCaps-NewBorrowCap: borrow
  //   cfg: numBorrowCaps = newBorrowCaps.length
  //   cfg: require(bool,string)(numMarkets != 0 && numMarkets == numBorrowCaps,invalid input)
  //   cfg: borrowCaps[address(bTokens[i])] = newBorrowCaps[i]
  //   cfg: NewBorrowCap(bTokens[i],newBorrowCaps[i])
  // Comptroller-setGuardian-NewGuardian: pause
  //   cfg: fail(Error.UNAUTHORIZED,FailureInfo.SET_PAUSE_GUARDIAN_OWNER_CHECK)
  //   cfg: oldGuardian = guardian
  //   cfg: guardian = newGuardian
  //   cfg: NewGuardian(oldGuardian,guardian)
  // Comptroller-setLiquidityMining-NewLiquidityMining: 
  //   cfg: require(bool,string)(LiquidityMiningInterface(newLiquidityMining).comptroller() == address(this),mismatch comptroller)
  //   cfg: oldLiquidityMining = liquidityMining
  //   cfg: liquidityMining = newLiquidityMining
  //   cfg: NewLiquidityMining(oldLiquidityMining,liquidityMining)
  // Comptroller-setCreditLimitManager-NewCreditLimitManager: 
  //   cfg: oldCreditLimitManager = creditLimitManager
  //   cfg: creditLimitManager = newCreditLimitManager
  //   cfg: NewCreditLimitManager(oldCreditLimitManager,creditLimitManager)
  // Comptroller-setMintPaused-ActionPaused: mint, pause
  //   cfg: mintGuardianPaused[address(bToken)] = state
  // Comptroller-setBorrowPaused-ActionPaused: borrow, pause
  //   cfg: borrowGuardianPaused[address(bToken)] = state
  // Comptroller-setFlashloanPaused-ActionPaused: pause
  //   cfg: flashloanGuardianPaused[address(bToken)] = state
  // Comptroller-setTransferPaused-ActionPaused: pause, transfer
  //   cfg: transferGuardianPaused = state
  // Comptroller-setSeizePaused-ActionPaused: pause
  //   cfg: seizeGuardianPaused = state
  // Comptroller-setCreditLimitInternal-CreditLimitChanged: 
  //   cfg: _creditLimits[protocol][market] = creditLimit
  // ComptrollerErrorReporter-fail-Failure: 
  // ComptrollerErrorReporter-failOpaque-Failure: 
  // TokenErrorReporter-fail-Failure: 
  // TokenErrorReporter-failOpaque-Failure: 
  // Unitroller-setPendingImplementation-NewPendingImplementation: 
  //   cfg: oldPendingImplementation = pendingComptrollerImplementation
  //   cfg: pendingComptrollerImplementation = newPendingImplementation
  //   cfg: NewPendingImplementation(oldPendingImplementation,pendingComptrollerImplementation)
  // Unitroller-acceptImplementation-NewImplementation: 
  //   cfg: msg.sender != pendingComptrollerImplementation || pendingComptrollerImplementation == address(0)
  //   cfg: oldImplementation = comptrollerImplementation
  //   cfg: oldPendingImplementation = pendingComptrollerImplementation
  //   cfg: comptrollerImplementation = pendingComptrollerImplementation
  //   cfg: pendingComptrollerImplementation = address(0)
  // Unitroller-acceptImplementation-NewPendingImplementation: 
  //   cfg: msg.sender != pendingComptrollerImplementation || pendingComptrollerImplementation == address(0)
  //   cfg: oldImplementation = comptrollerImplementation
  //   cfg: oldPendingImplementation = pendingComptrollerImplementation
  //   cfg: comptrollerImplementation = pendingComptrollerImplementation
  //   cfg: pendingComptrollerImplementation = address(0)
  // Unitroller-setPendingAdmin-NewPendingAdmin: 
  //   cfg: oldPendingAdmin = pendingAdmin
  //   cfg: pendingAdmin = newPendingAdmin
  //   cfg: NewPendingAdmin(oldPendingAdmin,newPendingAdmin)
  // Unitroller-acceptAdmin-NewAdmin: 
  //   cfg: msg.sender != pendingAdmin || msg.sender == address(0)
  //   cfg: fail(Error.UNAUTHORIZED,FailureInfo.ACCEPT_ADMIN_PENDING_ADMIN_CHECK)
  //   cfg: oldAdmin = admin
  //   cfg: oldPendingAdmin = pendingAdmin
  //   cfg: admin = pendingAdmin
  // Unitroller-acceptAdmin-NewPendingAdmin: 
  //   cfg: msg.sender != pendingAdmin || msg.sender == address(0)
  //   cfg: fail(Error.UNAUTHORIZED,FailureInfo.ACCEPT_ADMIN_PENDING_ADMIN_CHECK)
  //   cfg: oldAdmin = admin
  //   cfg: oldPendingAdmin = pendingAdmin
  //   cfg: admin = pendingAdmin
  // BToken-approve-Approval: transfer
  //   cfg: transferAllowances[src][spender] = amount
  // BToken-accrueInterest-AccrueInterest: borrow
  //   cfg: accrualBlockTimestampPrior = accrualBlockTimestamp
  //   cfg: accrualBlockTimestampPrior == currentBlockTimestamp
  //   cfg: borrowsPrior = totalBorrows
  //   cfg: reservesPrior = totalReserves
  //   cfg: borrowIndexPrior = borrowIndex
  // BToken-borrowFresh-Borrow: borrow, freshness-check, transfer
  //   cfg: require(bool,string)(accrualBlockTimestamp == getBlockTimestamp(),market is stale)
  //   cfg: vars.accountBorrows = borrowBalanceStoredInternal(borrower)
  //   cfg: vars.accountBorrowsNew = add_(vars.accountBorrows,borrowAmount)
  //   cfg: vars.totalBorrowsNew = add_(totalBorrows,borrowAmount)
  //   cfg: accountBorrows[borrower].principal = vars.accountBorrowsNew
  // BToken-repayBorrowFresh-RepayBorrow: borrow, freshness-check, transfer
  //   cfg: require(bool,string)(accrualBlockTimestamp == getBlockTimestamp(),market is stale)
  //   cfg: vars.borrowerIndex = accountBorrows[borrower].interestIndex
  //   cfg: vars.accountBorrows = borrowBalanceStoredInternal(borrower)
  //   cfg: vars.repayAmount = vars.accountBorrows
  //   cfg: vars.accountBorrowsNew = sub_(vars.accountBorrows,vars.actualRepayAmount)
  // BToken-liquidateBorrowFresh-LiquidateBorrow: borrow, freshness-check, liquidate
  //   cfg: require(bool,string)(accrualBlockTimestamp == getBlockTimestamp(),market is stale)
  //   cfg: require(bool,string)(bTokenCollateral.accrualBlockTimestamp() == getBlockTimestamp(),market is stale)
  // BToken-setPendingAdmin-NewPendingAdmin: 
  //   cfg: oldPendingAdmin = pendingAdmin
  //   cfg: pendingAdmin = newPendingAdmin
  //   cfg: NewPendingAdmin(oldPendingAdmin,newPendingAdmin)
  // BToken-acceptAdmin-NewAdmin: 
  //   cfg: msg.sender != pendingAdmin || msg.sender == address(0)
  //   cfg: fail(Error.UNAUTHORIZED,FailureInfo.ACCEPT_ADMIN_PENDING_ADMIN_CHECK)
  //   cfg: oldAdmin = admin
  //   cfg: oldPendingAdmin = pendingAdmin
  //   cfg: admin = pendingAdmin
  // BToken-acceptAdmin-NewPendingAdmin: 
  //   cfg: msg.sender != pendingAdmin || msg.sender == address(0)
  //   cfg: fail(Error.UNAUTHORIZED,FailureInfo.ACCEPT_ADMIN_PENDING_ADMIN_CHECK)
  //   cfg: oldAdmin = admin
  //   cfg: oldPendingAdmin = pendingAdmin
  //   cfg: admin = pendingAdmin
  // BToken-setComptroller-NewComptroller: 
  //   cfg: fail(Error.UNAUTHORIZED,FailureInfo.SET_COMPTROLLER_OWNER_CHECK)
  //   cfg: oldComptroller = comptroller
  //   cfg: require(bool,string)(newComptroller.isComptroller(),not comptroller)
  //   cfg: comptroller = newComptroller
  //   cfg: NewComptroller(oldComptroller,newComptroller)
  // BToken-setReserveFactorFresh-NewReserveFactor: 
  //   cfg: newReserveFactorMantissa > reserveFactorMaxMantissa
  //   cfg: oldReserveFactorMantissa = reserveFactorMantissa
  //   cfg: reserveFactorMantissa = newReserveFactorMantissa
  //   cfg: NewReserveFactor(oldReserveFactorMantissa,newReserveFactorMantissa)
  // BToken-addReservesFresh-ReservesAdded: transfer
  //   cfg: totalReservesNew = add_(totalReserves,actualAddAmount)
  //   cfg: totalReserves = totalReservesNew
  //   cfg: ReservesAdded(msg.sender,actualAddAmount,totalReservesNew)
  // BToken-reduceReservesFresh-ReservesReduced: transfer
  //   cfg: reduceAmount > totalReserves
  //   cfg: totalReservesNew = sub_(totalReserves,reduceAmount)
  //   cfg: totalReserves = totalReservesNew
  //   cfg: ReservesReduced(admin,reduceAmount,totalReservesNew)
  // BToken-setInterestRateModelFresh-NewMarketInterestRateModel: 
  //   cfg: oldInterestRateModel = interestRateModel
  //   cfg: require(bool,string)(newInterestRateModel.isInterestRateModel(),invalid IRM)
  //   cfg: interestRateModel = newInterestRateModel
  //   cfg: NewMarketInterestRateModel(oldInterestRateModel,newInterestRateModel)
  // ComptrollerErrorReporter-fail-Failure: 
  // ComptrollerErrorReporter-failOpaque-Failure: 
  // TokenErrorReporter-fail-Failure: 
  // TokenErrorReporter-failOpaque-Failure: 
  // ComptrollerErrorReporter-fail-Failure: 
  // ComptrollerErrorReporter-failOpaque-Failure: 
  // TokenErrorReporter-fail-Failure: 
  // TokenErrorReporter-failOpaque-Failure: 
  // BToken-approve-Approval: transfer
  //   cfg: transferAllowances[src][spender] = amount
  // BToken-accrueInterest-AccrueInterest: borrow
  //   cfg: accrualBlockTimestampPrior = accrualBlockTimestamp
  //   cfg: accrualBlockTimestampPrior == currentBlockTimestamp
  //   cfg: borrowsPrior = totalBorrows
  //   cfg: reservesPrior = totalReserves
  //   cfg: borrowIndexPrior = borrowIndex
  // BToken-borrowFresh-Borrow: borrow, freshness-check, transfer
  //   cfg: require(bool,string)(accrualBlockTimestamp == getBlockTimestamp(),market is stale)
  //   cfg: vars.accountBorrows = borrowBalanceStoredInternal(borrower)
  //   cfg: vars.accountBorrowsNew = add_(vars.accountBorrows,borrowAmount)
  //   cfg: vars.totalBorrowsNew = add_(totalBorrows,borrowAmount)
  //   cfg: accountBorrows[borrower].principal = vars.accountBorrowsNew
  // BToken-repayBorrowFresh-RepayBorrow: borrow, freshness-check, transfer
  //   cfg: require(bool,string)(accrualBlockTimestamp == getBlockTimestamp(),market is stale)
  //   cfg: vars.borrowerIndex = accountBorrows[borrower].interestIndex
  //   cfg: vars.accountBorrows = borrowBalanceStoredInternal(borrower)
  //   cfg: vars.repayAmount = vars.accountBorrows
  //   cfg: vars.accountBorrowsNew = sub_(vars.accountBorrows,vars.actualRepayAmount)
  // BToken-liquidateBorrowFresh-LiquidateBorrow: borrow, freshness-check, liquidate
  //   cfg: require(bool,string)(accrualBlockTimestamp == getBlockTimestamp(),market is stale)
  //   cfg: require(bool,string)(bTokenCollateral.accrualBlockTimestamp() == getBlockTimestamp(),market is stale)
  // BToken-setPendingAdmin-NewPendingAdmin: 
  //   cfg: oldPendingAdmin = pendingAdmin
  //   cfg: pendingAdmin = newPendingAdmin
  //   cfg: NewPendingAdmin(oldPendingAdmin,newPendingAdmin)
  // BToken-acceptAdmin-NewAdmin: 
  //   cfg: msg.sender != pendingAdmin || msg.sender == address(0)
  //   cfg: fail(Error.UNAUTHORIZED,FailureInfo.ACCEPT_ADMIN_PENDING_ADMIN_CHECK)
  //   cfg: oldAdmin = admin
  //   cfg: oldPendingAdmin = pendingAdmin
  //   cfg: admin = pendingAdmin
  // BToken-acceptAdmin-NewPendingAdmin: 
  //   cfg: msg.sender != pendingAdmin || msg.sender == address(0)
  //   cfg: fail(Error.UNAUTHORIZED,FailureInfo.ACCEPT_ADMIN_PENDING_ADMIN_CHECK)
  //   cfg: oldAdmin = admin
  //   cfg: oldPendingAdmin = pendingAdmin
  //   cfg: admin = pendingAdmin
  // BToken-setComptroller-NewComptroller: 
  //   cfg: fail(Error.UNAUTHORIZED,FailureInfo.SET_COMPTROLLER_OWNER_CHECK)
  //   cfg: oldComptroller = comptroller
  //   cfg: require(bool,string)(newComptroller.isComptroller(),not comptroller)
  //   cfg: comptroller = newComptroller
  //   cfg: NewComptroller(oldComptroller,newComptroller)
  // BToken-setReserveFactorFresh-NewReserveFactor: 
  //   cfg: newReserveFactorMantissa > reserveFactorMaxMantissa
  //   cfg: oldReserveFactorMantissa = reserveFactorMantissa
  //   cfg: reserveFactorMantissa = newReserveFactorMantissa
  //   cfg: NewReserveFactor(oldReserveFactorMantissa,newReserveFactorMantissa)
  // BToken-addReservesFresh-ReservesAdded: transfer
  //   cfg: totalReservesNew = add_(totalReserves,actualAddAmount)
  //   cfg: totalReserves = totalReservesNew
  //   cfg: ReservesAdded(msg.sender,actualAddAmount,totalReservesNew)
  // BToken-reduceReservesFresh-ReservesReduced: transfer
  //   cfg: reduceAmount > totalReserves
  //   cfg: totalReservesNew = sub_(totalReserves,reduceAmount)
  //   cfg: totalReserves = totalReservesNew
  //   cfg: ReservesReduced(admin,reduceAmount,totalReservesNew)
  // BToken-setInterestRateModelFresh-NewMarketInterestRateModel: 
  //   cfg: oldInterestRateModel = interestRateModel
  //   cfg: require(bool,string)(newInterestRateModel.isInterestRateModel(),invalid IRM)
  //   cfg: interestRateModel = newInterestRateModel
  //   cfg: NewMarketInterestRateModel(oldInterestRateModel,newInterestRateModel)
  // ComptrollerErrorReporter-fail-Failure: 
  // ComptrollerErrorReporter-failOpaque-Failure: 
  // TokenErrorReporter-fail-Failure: 
  // TokenErrorReporter-failOpaque-Failure: 
  // BToken-approve-Approval: transfer
  //   cfg: transferAllowances[src][spender] = amount
  // BToken-accrueInterest-AccrueInterest: borrow
  //   cfg: accrualBlockTimestampPrior = accrualBlockTimestamp
  //   cfg: accrualBlockTimestampPrior == currentBlockTimestamp
  //   cfg: borrowsPrior = totalBorrows
  //   cfg: reservesPrior = totalReserves
  //   cfg: borrowIndexPrior = borrowIndex
  // BToken-borrowFresh-Borrow: borrow, freshness-check, transfer
  //   cfg: require(bool,string)(accrualBlockTimestamp == getBlockTimestamp(),market is stale)
  //   cfg: vars.accountBorrows = borrowBalanceStoredInternal(borrower)
  //   cfg: vars.accountBorrowsNew = add_(vars.accountBorrows,borrowAmount)
  //   cfg: vars.totalBorrowsNew = add_(totalBorrows,borrowAmount)
  //   cfg: accountBorrows[borrower].principal = vars.accountBorrowsNew
  // BToken-repayBorrowFresh-RepayBorrow: borrow, freshness-check, transfer
  //   cfg: require(bool,string)(accrualBlockTimestamp == getBlockTimestamp(),market is stale)
  //   cfg: vars.borrowerIndex = accountBorrows[borrower].interestIndex
  //   cfg: vars.accountBorrows = borrowBalanceStoredInternal(borrower)
  //   cfg: vars.repayAmount = vars.accountBorrows
  //   cfg: vars.accountBorrowsNew = sub_(vars.accountBorrows,vars.actualRepayAmount)
  // BToken-liquidateBorrowFresh-LiquidateBorrow: borrow, freshness-check, liquidate
  //   cfg: require(bool,string)(accrualBlockTimestamp == getBlockTimestamp(),market is stale)
  //   cfg: require(bool,string)(bTokenCollateral.accrualBlockTimestamp() == getBlockTimestamp(),market is stale)
  // BToken-setPendingAdmin-NewPendingAdmin: 
  //   cfg: oldPendingAdmin = pendingAdmin
  //   cfg: pendingAdmin = newPendingAdmin
  //   cfg: NewPendingAdmin(oldPendingAdmin,newPendingAdmin)
  // BToken-acceptAdmin-NewAdmin: 
  //   cfg: msg.sender != pendingAdmin || msg.sender == address(0)
  //   cfg: fail(Error.UNAUTHORIZED,FailureInfo.ACCEPT_ADMIN_PENDING_ADMIN_CHECK)
  //   cfg: oldAdmin = admin
  //   cfg: oldPendingAdmin = pendingAdmin
  //   cfg: admin = pendingAdmin
  // BToken-acceptAdmin-NewPendingAdmin: 
  //   cfg: msg.sender != pendingAdmin || msg.sender == address(0)
  //   cfg: fail(Error.UNAUTHORIZED,FailureInfo.ACCEPT_ADMIN_PENDING_ADMIN_CHECK)
  //   cfg: oldAdmin = admin
  //   cfg: oldPendingAdmin = pendingAdmin
  //   cfg: admin = pendingAdmin
  // BToken-setComptroller-NewComptroller: 
  //   cfg: fail(Error.UNAUTHORIZED,FailureInfo.SET_COMPTROLLER_OWNER_CHECK)
  //   cfg: oldComptroller = comptroller
  //   cfg: require(bool,string)(newComptroller.isComptroller(),not comptroller)
  //   cfg: comptroller = newComptroller
  //   cfg: NewComptroller(oldComptroller,newComptroller)
  // BToken-setReserveFactorFresh-NewReserveFactor: 
  //   cfg: newReserveFactorMantissa > reserveFactorMaxMantissa
  //   cfg: oldReserveFactorMantissa = reserveFactorMantissa
  //   cfg: reserveFactorMantissa = newReserveFactorMantissa
  //   cfg: NewReserveFactor(oldReserveFactorMantissa,newReserveFactorMantissa)
  // BToken-addReservesFresh-ReservesAdded: transfer
  //   cfg: totalReservesNew = add_(totalReserves,actualAddAmount)
  //   cfg: totalReserves = totalReservesNew
  //   cfg: ReservesAdded(msg.sender,actualAddAmount,totalReservesNew)
  // BToken-reduceReservesFresh-ReservesReduced: transfer
  //   cfg: reduceAmount > totalReserves
  //   cfg: totalReservesNew = sub_(totalReserves,reduceAmount)
  //   cfg: totalReserves = totalReservesNew
  //   cfg: ReservesReduced(admin,reduceAmount,totalReservesNew)
  // BToken-setInterestRateModelFresh-NewMarketInterestRateModel: 
  //   cfg: oldInterestRateModel = interestRateModel
  //   cfg: require(bool,string)(newInterestRateModel.isInterestRateModel(),invalid IRM)
  //   cfg: interestRateModel = newInterestRateModel
  //   cfg: NewMarketInterestRateModel(oldInterestRateModel,newInterestRateModel)
  // ComptrollerErrorReporter-fail-Failure: 
  // ComptrollerErrorReporter-failOpaque-Failure: 
  // TokenErrorReporter-fail-Failure: 
  // TokenErrorReporter-failOpaque-Failure: 
  // Unitroller-setPendingImplementation-NewPendingImplementation: 
  //   cfg: oldPendingImplementation = pendingComptrollerImplementation
  //   cfg: pendingComptrollerImplementation = newPendingImplementation
  //   cfg: NewPendingImplementation(oldPendingImplementation,pendingComptrollerImplementation)
  // Unitroller-acceptImplementation-NewImplementation: 
  //   cfg: msg.sender != pendingComptrollerImplementation || pendingComptrollerImplementation == address(0)
  //   cfg: oldImplementation = comptrollerImplementation
  //   cfg: oldPendingImplementation = pendingComptrollerImplementation
  //   cfg: comptrollerImplementation = pendingComptrollerImplementation
  //   cfg: pendingComptrollerImplementation = address(0)
  // Unitroller-acceptImplementation-NewPendingImplementation: 
  //   cfg: msg.sender != pendingComptrollerImplementation || pendingComptrollerImplementation == address(0)
  //   cfg: oldImplementation = comptrollerImplementation
  //   cfg: oldPendingImplementation = pendingComptrollerImplementation
  //   cfg: comptrollerImplementation = pendingComptrollerImplementation
  //   cfg: pendingComptrollerImplementation = address(0)
  // Unitroller-setPendingAdmin-NewPendingAdmin: 
  //   cfg: oldPendingAdmin = pendingAdmin
  //   cfg: pendingAdmin = newPendingAdmin
  //   cfg: NewPendingAdmin(oldPendingAdmin,newPendingAdmin)
  // Unitroller-acceptAdmin-NewAdmin: 
  //   cfg: msg.sender != pendingAdmin || msg.sender == address(0)
  //   cfg: fail(Error.UNAUTHORIZED,FailureInfo.ACCEPT_ADMIN_PENDING_ADMIN_CHECK)
  //   cfg: oldAdmin = admin
  //   cfg: oldPendingAdmin = pendingAdmin
  //   cfg: admin = pendingAdmin
  // Unitroller-acceptAdmin-NewPendingAdmin: 
  //   cfg: msg.sender != pendingAdmin || msg.sender == address(0)
  //   cfg: fail(Error.UNAUTHORIZED,FailureInfo.ACCEPT_ADMIN_PENDING_ADMIN_CHECK)
  //   cfg: oldAdmin = admin
  //   cfg: oldPendingAdmin = pendingAdmin
  //   cfg: admin = pendingAdmin
endmodule
