requires "domains.md"

module DSC-GUARD-BLIZZ-LUNA-SYNTAX
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

module DSC-GUARD-BLIZZ-LUNA
  imports DSC-GUARD-BLIZZ-LUNA-SYNTAX
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
  // BaseUpgradeabilityProxy-upgradeTo-Upgraded: 
  // LendingPoolConfigurator-initReserve-ReserveInitialized: 
  // LendingPoolConfigurator-updateAToken-ATokenUpgraded: 
  // LendingPoolConfigurator-updateStableDebtToken-StableDebtTokenUpgraded: 
  // LendingPoolConfigurator-updateVariableDebtToken-VariableDebtTokenUpgraded: 
  // LendingPoolConfigurator-enableBorrowingOnReserve-BorrowingEnabledOnReserve: borrow
  // LendingPoolConfigurator-disableBorrowingOnReserve-BorrowingDisabledOnReserve: borrow
  // LendingPoolConfigurator-configureReserveAsCollateral-CollateralConfigurationChanged: 
  // LendingPoolConfigurator-enableReserveStableRate-StableRateEnabledOnReserve: borrow
  // LendingPoolConfigurator-disableReserveStableRate-StableRateDisabledOnReserve: borrow
  // LendingPoolConfigurator-activateReserve-ReserveActivated: 
  // LendingPoolConfigurator-deactivateReserve-ReserveDeactivated: 
  // LendingPoolConfigurator-freezeReserve-ReserveFrozen: 
  // LendingPoolConfigurator-unfreezeReserve-ReserveUnfrozen: 
  // LendingPoolConfigurator-setReserveFactor-ReserveFactorChanged: 
  // LendingPoolConfigurator-setReserveInterestRateStrategyAddress-ReserveInterestRateStrategyChanged: 
  // BaseUpgradeabilityProxy-upgradeTo-Upgraded: 
  // LendingPoolConfigurator-initReserve-ReserveInitialized: 
  // LendingPoolConfigurator-updateAToken-ATokenUpgraded: 
  // LendingPoolConfigurator-updateStableDebtToken-StableDebtTokenUpgraded: 
  // LendingPoolConfigurator-updateVariableDebtToken-VariableDebtTokenUpgraded: 
  // LendingPoolConfigurator-enableBorrowingOnReserve-BorrowingEnabledOnReserve: borrow
  // LendingPoolConfigurator-disableBorrowingOnReserve-BorrowingDisabledOnReserve: borrow
  // LendingPoolConfigurator-configureReserveAsCollateral-CollateralConfigurationChanged: 
  // LendingPoolConfigurator-enableReserveStableRate-StableRateEnabledOnReserve: borrow
  // LendingPoolConfigurator-disableReserveStableRate-StableRateDisabledOnReserve: borrow
  // LendingPoolConfigurator-activateReserve-ReserveActivated: 
  // LendingPoolConfigurator-deactivateReserve-ReserveDeactivated: 
  // LendingPoolConfigurator-freezeReserve-ReserveFrozen: 
  // LendingPoolConfigurator-unfreezeReserve-ReserveUnfrozen: 
  // LendingPoolConfigurator-setReserveFactor-ReserveFactorChanged: 
  // LendingPoolConfigurator-setReserveInterestRateStrategyAddress-ReserveInterestRateStrategyChanged: 
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
  // BaseUpgradeabilityProxy-upgradeTo-Upgraded: 
  // LendingPoolConfigurator-initReserve-ReserveInitialized: 
  // LendingPoolConfigurator-updateAToken-ATokenUpgraded: 
  // LendingPoolConfigurator-updateStableDebtToken-StableDebtTokenUpgraded: 
  // LendingPoolConfigurator-updateVariableDebtToken-VariableDebtTokenUpgraded: 
  // LendingPoolConfigurator-enableBorrowingOnReserve-BorrowingEnabledOnReserve: borrow
  // LendingPoolConfigurator-disableBorrowingOnReserve-BorrowingDisabledOnReserve: borrow
  // LendingPoolConfigurator-configureReserveAsCollateral-CollateralConfigurationChanged: 
  // LendingPoolConfigurator-enableReserveStableRate-StableRateEnabledOnReserve: borrow
  // LendingPoolConfigurator-disableReserveStableRate-StableRateDisabledOnReserve: borrow
  // LendingPoolConfigurator-activateReserve-ReserveActivated: 
  // LendingPoolConfigurator-deactivateReserve-ReserveDeactivated: 
  // LendingPoolConfigurator-freezeReserve-ReserveFrozen: 
  // LendingPoolConfigurator-unfreezeReserve-ReserveUnfrozen: 
  // LendingPoolConfigurator-setReserveFactor-ReserveFactorChanged: 
  // LendingPoolConfigurator-setReserveInterestRateStrategyAddress-ReserveInterestRateStrategyChanged: 
  // IncentivizedERC20-transfer-Transfer: transfer
  // IncentivizedERC20-transferFrom-Transfer: transfer
  // IncentivizedERC20-approve-Approval: 
  //   cfg: _allowances[owner][spender] = amount
  // AToken-initialize-Initialized: 
  //   cfg: DOMAIN_SEPARATOR = keccak256(bytes)(abi.encode(EIP712_DOMAIN,keccak256(bytes)(bytes(aTokenName)),keccak256(bytes)(EIP712_REVISION),chainId,address(this)))
  //   cfg: _pool = pool
  //   cfg: _treasury = treasury
  //   cfg: _underlyingAsset = underlyingAsset
  //   cfg: _incentivesController = incentivesController
  // AToken-burn-Transfer: transfer
  // AToken-burn-Burn: transfer
  // AToken-mint-Transfer: mint, transfer
  // AToken-mint-Mint: mint, transfer
  // AToken-mintToTreasury-Transfer: mint, transfer
  // AToken-mintToTreasury-Mint: mint, transfer
  // AToken-transferOnLiquidation-Transfer: transfer
  // AToken-transfer-BalanceTransfer: transfer
  // BaseUpgradeabilityProxy-upgradeTo-Upgraded: 
  // LendingPoolConfigurator-initReserve-ReserveInitialized: 
  // LendingPoolConfigurator-updateAToken-ATokenUpgraded: 
  // LendingPoolConfigurator-updateStableDebtToken-StableDebtTokenUpgraded: 
  // LendingPoolConfigurator-updateVariableDebtToken-VariableDebtTokenUpgraded: 
  // LendingPoolConfigurator-enableBorrowingOnReserve-BorrowingEnabledOnReserve: borrow
  // LendingPoolConfigurator-disableBorrowingOnReserve-BorrowingDisabledOnReserve: borrow
  // LendingPoolConfigurator-configureReserveAsCollateral-CollateralConfigurationChanged: 
  // LendingPoolConfigurator-enableReserveStableRate-StableRateEnabledOnReserve: borrow
  // LendingPoolConfigurator-disableReserveStableRate-StableRateDisabledOnReserve: borrow
  // LendingPoolConfigurator-activateReserve-ReserveActivated: 
  // LendingPoolConfigurator-deactivateReserve-ReserveDeactivated: 
  // LendingPoolConfigurator-freezeReserve-ReserveFrozen: 
  // LendingPoolConfigurator-unfreezeReserve-ReserveUnfrozen: 
  // LendingPoolConfigurator-setReserveFactor-ReserveFactorChanged: 
  // LendingPoolConfigurator-setReserveInterestRateStrategyAddress-ReserveInterestRateStrategyChanged: 
endmodule
