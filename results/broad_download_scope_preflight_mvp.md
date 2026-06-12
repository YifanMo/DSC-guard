# Broad Download-Scope Preflight

This preflight uses existing remote broad-search index rows and local seed evidence. It does not download receipts or execute chain calls.

- MVP case required in selected subset: `all`
- MVP covered by selected subset: `True`
- Seed/evaluation cases: `6`
- Seed cases already materialized: `6`
- Remote candidate rows: `111`
- Remote candidate tx/log references: `333`
- Remote unique candidate tx references: `271`
- Queue candidates eligible for local download: `111`
- Eligible queue receipt/log bundles: `333`
- Eligible queue estimated RPC requests: `999`
- Selected download candidates: `111`
- Selected receipt/log bundles: `333`
- Selected estimated RPC requests: `999`
- Selected estimated ABI requests: `222`
- Target local bundles: `3000`
- Target exceeded: `False`
- Requires stricter rules: `False`
- MVP-overlap candidates in eligible queue: `49`
- MVP-overlap txs in selected subset: `65`

## MVP Case Coverage

| case | seed_materialized | remote_overlap_candidates | selected_remote_candidates | selected_bundles | selected_rpc |
|---|---:|---:|---:|---:|---:|
| ploutos | True | 0 | 0 | 0 | 0 |
| moonwell_cbeth | True | 0 | 0 | 0 | 0 |
| moonwell_wrseth | True | 0 | 0 | 0 | 0 |
| blueberry_faulty_oracle | True | 0 | 0 | 0 | 0 |
| venus_luna | True | 0 | 0 | 0 | 0 |
| blizz_luna | True | 49 | 49 | 147 | 441 |

## Selected Candidates

Selection is gate-only: every A/B candidate satisfying fixed evidence-closure predicates is included. If the count is too high, the next experiment should tighten the semantic gates instead of truncating this table.

| candidate_id | trigger_tx |
|---|---|
| `broad-000054` | `0x1bec6d78641099ceb20fb36ab32edaa089569cef8b507a7c79743cf4e5fd2ae5` |
| `broad-000032` | `0xeaea10d937adb16273baa31419b7869a17403dde35df573d3d35d5933724e697` |
| `broad-000055` | `0x2b31dfa44aa31d6e988815bec6f60b1d481b314f74020711b3f947aea2cd6861` |
| `broad-000030` | `0xfe1cf5aa62c8dc4ec3f23f15f3160ed2addfe32d92f0494411bbadda6aad1403` |
| `broad-000100` | `0x87f8d3cc139cebd96f8b65322df6946440686cb07256707c6e890038ce4ed134` |
| `broad-000067` | `0x286674d12df376a777c04def5230b93f3d3aa19a06a4de68d5ba7741f9682730` |
| `broad-000083` | `0x72f02a1ea977978f267f2dcd50a10f9558e03575445df0c377c19de81932ed68` |
| `broad-000022` | `0x8020588a3910050ab4fdcec766d97eb07b14c86cb49645f0d759b1a4da9ff58f` |
| `broad-000092` | `0x567cf4058ecf6ec5ea0aec8b200fe0f970455600322fed1a0eca21e2d6a539e1` |
| `broad-000026` | `0x86a34420a9741a8e8679e074b1572cbf3ac52b706313f417b679b6a0f5556bab` |
| `broad-000043` | `0x6061d3802e0ca167dd68a58cd194734221ab151fc22026877cb9e517a7abf941` |
| `broad-000003` | `0xb3051ce0f7663c86f6d76929e8fffe610df69368a8bdb7cea475a44dd307e658` |
| `broad-000040` | `0x49a3e5a0993c7060036a9efcdad6a183543da7df19c9686a5da7544ab0614500` |
| `broad-000070` | `0xfc8d9f479c20ff0b8c9fdd4d3cdc53d945c47126c160377172c5635bbeed8eea` |
| `broad-000007` | `0xa6ae98b4265e39fed199c4804298cbde318d2fda472cc54c051deb007411293f` |
| `broad-000009` | `0x40c9dbbf5fa5be940b40e67c85c5a3ed7cd34ee4cdc76068c2fe926f31ddec98` |
| `broad-000010` | `0x4a85ae6b54fc7de2679400e02e066260770cdb89f6d7122ac086641c94ecd6dc` |
| `broad-000013` | `0xa1807e6af08c058378b56be4fd18204c85272c3c21e157cb948254766052bedb` |
| `broad-000011` | `0xa8459c895fb31ea8ba24b2fa26158d19dab4b4fef8dc47187dd13b9f9ea87af0` |
| `broad-000012` | `0xf6fc22ee487c5d7dcfaefd8e5686677ac7c8d98453f4150e665adab12a438615` |
| `broad-000008` | `0xfd335987476670d5290c414427def7784ab52a867aba72a26d92c41439172ece` |
| `broad-000015` | `0x8f3bd365403b5f98445e6f2b06fabd95ab5d7f0cf333897f94248f56abc2fc76` |
| `broad-000019` | `0x211d4e0be25abca2b5f64cc992c802a0646126bb001457fe69b05a14cca83867` |
| `broad-000028` | `0xfd95cc820ee62b155722e72bab6bc2da6cba53eca1ba3bfb10a292dfac0b227f` |
| `broad-000037` | `0x6a2fe71d2c8f3c3e24a125a45c7bdec8a7ec6598bae59bb352c02b233670acf2` |
| `broad-000041` | `0x47441e42c61bc593da0adcf72e84b6fdfda24e177b9ee097250fc56d23d3bda6` |
| `broad-000042` | `0xe627c2b017b12059bffac55a120dc90790447965105680073d10cccaccc79040` |
| `broad-000045` | `0xc26415a9e481b919cdf692bc5cbdd72edb4c6d90b97b8333f716c1ad000727c4` |
| `broad-000047` | `0x230f1b8701d6488910be14bd580f653c735f6b510ecc3efaacc3c2242c61fe8b` |
| `broad-000048` | `0x58e0a9981944dc8c63aab4bac10ddd4671910acf2a5b2009ea556410fbdcfb59` |
| `broad-000060` | `0x2056107d32582e0ba799c3eb58b9a4d2a4047ed02e4265b8c1f19fb26ad565af` |
| `broad-000064` | `0xd17dfd60283e7597c0349d80c4f4cae066aee806bf5238e62c4b59ec212e8325` |
| `broad-000066` | `0x1ca8ca2cebb783dfa526b4d0eb34f218c7cbb1081bd9b661277ffb628e31129d` |
| `broad-000069` | `0x14dc558fd51cd9568cd7b7ffba168762777a38cf5f964c9678d88dccfd1c2cd9` |
| `broad-000073` | `0xa5ca5b1c396420a05e569ea229fd5cc45e00294cc5e4d8de48159a5cb41d2f06` |
| `broad-000074` | `0x8ccf6816c047ba8ace55d31d4ef4c4cb9ecf1d68fb868189fdffcbbea6a0b7b1` |
| `broad-000079` | `0x7d152b9961644bb890f88f9bdfce29029955f9552ad40e49acd3070ce801487c` |
| `broad-000077` | `0x8f3aea7b9243a6ed47a1079d48fe32dd7f5888b2ec0ac97f76484afcefff379c` |
| `broad-000085` | `0xda88570403c5cbf72a8245524d434e130b3753ac2b32826678a77e7a1c7f3109` |
| `broad-000096` | `0x433dc534609d69131acfd8611d4dafae2aa692ad02f36e4f1c757902b1b55eef` |
| `broad-000052` | `0xd88853a197488409f4e30bf17767fb3ca49cea58eb6b656a59fb840bb51ba221` |
| `broad-000105` | `0x67bda3e5365410a8fbf16aad29ed7deee9926c15cd29fa1bc45726b1386cb019` |
| `broad-000024` | `0x0c5f85e3da0e0105a9fd52876eb10f289fddf17d74e6143c2e9c391436b6ea45` |
| `broad-000020` | `0x91c69fbfdcd701a54105febd678c9e6bb1b778303aeea2327741569794662c87` |
| `broad-000029` | `0x81d7a418828106a9cfee160390ba79b5afcef386aa368ba9efd60eaf26111906` |
| `broad-000065` | `0xebbd5f855e9c1abc5a9cbabd2312cb3f2528933f81e30854bb01e526b9b3ab37` |
| `broad-000082` | `0x878688bce86ae3423e8163dbce03c5c7de5a995555f03721e8fae1b5cfe2cb81` |
| `broad-000090` | `0x7f308783bfea497318adcd05d8573317ea416f6c072b50e7c0e17eb843a501e4` |
| `broad-000109` | `0xf08fdc12e15b35d682841c983899c6688e12a24cd6583874d4467995122dbf0e` |
| `broad-000104` | `0xe48bf49cb9fd0e057e3a3d2caf7e699b7f634483216b1f88d42270d3aed603f5` |
| `broad-000021` | `0x6185e0008f318dc8a4329ac8b0fb409dc5c978766864f5e9e70cb884c3ea142d` |
| `broad-000001` | `0xad641aa9f1e6d2956e0f6387c1bfa272814a3dada22f98603f61ec706aaa8d0d` |
| `broad-000002` | `0x91c93e9a9310af0f86a7b4f57d778fab55329a85c8fba7986df08385cf8b9d55` |
| `broad-000025` | `0x8650c2b1af37095580723f6cc796b15489a33dd4b24ed34f77b63e26b848cfc0` |
| `broad-000076` | `0x4ea2a80df7bdf75f11dd44dc803153aae88df250d2c6840d8a2b9f67669af9da` |
| `broad-000033` | `0xf7aa4264633afa3718361a4bafeb9aa70d0a7b9b1a8410b5182d206f5e9dc398` |
| `broad-000088` | `0x514d7728d24692875c399fcfb396258206c82133f5d639dc6355fb3581cc5d8f` |
| `broad-000050` | `0xef28ed2ea525fe38c6c8c384683fff09125d6a7ede8985eef9682c9049e51f9e` |
| `broad-000111` | `0x2ea6bb37b83bc5b88d33018c693ac1e66fd67b8e950e0a63f9d49b4d55708751` |
| `broad-000027` | `0xb030793bcc836110c5a6c2b51c98facc6314e6b20490d958a6ea74760d88e7e1` |
| `broad-000034` | `0x0e7dc39f31a5662701d1ddce35f65d56e08ab1f2f0d80d1920d83ee69f21170a` |
| `broad-000004` | `0x70c86b2cc52e9261b8fb34e727dfd5d2912d80cfba3ad7cbf2ee7427e7212740` |
| `broad-000091` | `0xd1db888d943a6bfdd6ea445685ce658b18dfea0e1d6536908155173128ec3091` |
| `broad-000056` | `0xbe9fabcbdb102b1b105a1d39398959bf71edd2c4b52f1437c175a8719a23dd24` |
| `broad-000101` | `0x16fe7dbc97e581a9ce7b95ba82c47bd2a53a1aba8d8604591eb00fbd83945748` |
| `broad-000016` | `0x346d819a902adfa51ace39ee12b5a4ac9ef1bc337f179a4f0d9eb9a73ca142f1` |
| `broad-000057` | `0x38f0454ce57372cc6aa2bac59914218aa33adfe585eeff9ff6e5bbc3435ccc4c` |
| `broad-000084` | `0x1d7ab09b3488c38dddc3def494d7f03378f61d9e4c5f218cae744a4921e41bb9` |
| `broad-000005` | `0xf5f7904888c08f0ee4f268557330f6a340a46f1b2a83f25963d2d88eb66ddbbd` |
| `broad-000058` | `0x8c8d202f562f6db7db07251ce05e649f6e2e8ffe72a3ead47efed6c77b3bf684` |
| `broad-000006` | `0x767942d50aefba961928d7f154df6bbf19920c7c1247339bfeaac1dc5d0a7be0` |
| `broad-000044` | `0x6baa6af189acfc34a23293c78c40bfe567e5a1120a2182eaed03c47d6c7eaec2` |
| `broad-000014` | `0xca8c4ae44baa65722f7ed5baab3f87dbaa1744b1edac0fb64bcf24f1d711f9f0` |
| `broad-000017` | `0x0f96998e05943e9eb442e58a11573dfee90ca028d478ef505344402f1dccaee8` |
| `broad-000018` | `0xde2e9b246f6973351cac13c99331eb091832310be39c542ce5e33792715681ff` |
| `broad-000023` | `0x10a00c87b8e8778ef3e739461da327ee5cd0d81afe628bb907f4317185aee528` |
| `broad-000031` | `0xa2059a77f7353e8b96c088c3d2f0d26b8faa8665b0aee1988c72e0f2220c0a35` |
| `broad-000035` | `0xe990b57ad822379eb92a1e203686eae14816c3b5bfbc2fe5693028b92b1a4eeb` |
| `broad-000036` | `0xbc2b8b32f941beebd84bac10d10f271e7bc57d92cd72e4725bc788f4fbd3ff79` |
| `broad-000038` | `0xbb3b0ee6d9a475331962823e7656ad54cefe76d6cfe0869deba4cf7b7f81bbbb` |
| `broad-000046` | `0x140e816d37375734384ca622662b8d584584ee27da21469af976cdad5c173711` |
| `broad-000049` | `0xbe7911b086deb961340bf88e8f5b148147d00b55fdb76ec194bcb237f4aa3761` |
| `broad-000051` | `0x13154e691b92bfb0bc53c921cf57bf5d3b49c62500e41b6aa559299c6e5ff1d3` |
| `broad-000053` | `0x2c1b6d9ebc695325dda1c82f740f2a8ce7c66e97d302433e12f42a40f0078375` |
| `broad-000059` | `0x703641c50372261c4a24c733146fe4142ea05e40b75567146186cff04435066e` |
| `broad-000061` | `0x221243280fde3ab6ecc299cfe9e697ca058cbe53bf6f92cbeb2b14668358d1e9` |
| `broad-000062` | `0x9356bc14b772625a54f76a824e7ddd84afffd905fb4411c0f4ab721d6cfb6ed5` |
| `broad-000063` | `0x499fe92e73fe8c6c3b4e1f29d86dff171c47a6ed075f62d4a855bd986817838b` |
| `broad-000068` | `0x592ecc040ee9c0bbd86913ea333357e4664327b0c3adae30ceeaff6cafc3cc80` |
| `broad-000071` | `0x5228a7191e7de07c2111523ae2819df8a3f04972968369709ec7a1ebba3e035d` |
| `broad-000072` | `0x6ce3ec65711c814e94c0da3eb971dbaf5259416159287f9bd453654218d2f454` |
| `broad-000075` | `0xb32dc9d28ddceb6d4a1f829619b098e39159c84b75a9e20e4149ff8b4bf6e4af` |
| `broad-000078` | `0xa018b1d34937f9e63823fd985fbb7b7ffdf49d216c3ce25b46106a2472396a0d` |
| `broad-000080` | `0x245506cd22b541c6f3d3f42f418303f6b43167d3fd3edb00d48bd00ee6e35bd9` |
| `broad-000081` | `0xffafa3ffebf37b222079e53c3c31a7a19f46d408f11bf81ac72174316fadb9e4` |
| `broad-000086` | `0xfec15af06978a1ab5e0fa167a4389db13b847586f4daf0f8220e706ff332da85` |
| `broad-000087` | `0x89802f16563f0f2e25f7d2981d56310c84891345ec352bdb6cf267b0d2cca148` |
| `broad-000093` | `0xe6c318ca6f2704f38ebb50705171526e87a2a8ba7853c099e6f5d11be9e2c492` |
| `broad-000094` | `0xb3f8afec754877d4784337259cbc331b1bdb48225d266964e7b57dea7d3fb9bd` |
| `broad-000095` | `0xd463bd41a91d5fffd084f9c2dfbb7fb9f301627ed9d092652886393dc20f796c` |
| `broad-000098` | `0x36b412478ea3639faca0cb5170b7e3cd6b3e9d158a31aa18523c819b78de7a74` |
| `broad-000099` | `0x2c25943a72818cf06c1e56448784a1920b9e2a829401dc9b55ac0af7366ae8a4` |
| `broad-000102` | `0x14c3529bba72eecf1346be769637f384b03944e1614ca4e20f2ed7861fcbd5c3` |
| `broad-000103` | `0xc526800514d02802fd070cc7b2012a7008f463183e2a80da57e769233493f3bb` |
| `broad-000106` | `0x73ca25975a53b7c8e263d4ed4da4cb0ba4c4c88e3247c3538d8c05d113168025` |
| `broad-000108` | `0xb151055a3f8cff38cec0072931d60358c2ca94c791330fdfde30f027e962a241` |
| `broad-000110` | `0x51969b75e2fb60a3eaf2a35c99f51d8bbfbaeea261b7c44502416bf4a366331f` |
| `broad-000112` | `0xc7ea14c380180db59531e9a85ab15440d47631a45e71e098d15eea181ffcdf26` |
| `broad-000113` | `0x150c2376227852eac4068232ba457d5a34e1fe5c4267f67274db44ad4c69cfc9` |
| `broad-000114` | `0x7b4d29c8a29657921ed40421ade81efe66393cd55e0100df90cf4b6ec6918ec4` |
| `broad-000115` | `0x44eacdec4c91add69cee3c11f77d249c33701135f305cac52fb4219d6d4b774e` |

## Safety

- Read-only historical index rows only.
- No receipt download in this preflight.
- No write calls, private keys, transaction simulation, or future target prediction.
