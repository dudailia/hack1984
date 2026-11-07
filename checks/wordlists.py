"""
checks/wordlists.py: what counts as an ORDINARY word.

WHY
---
The provenance rule (provenance.py) protects "rare" words from the memo: names, codenames, odd numbers. A word is
rare if it is NOT ordinary English and NOT ordinary business/finance vocabulary. This file is that "ordinary" list.

HOW IT AFFECTS FALSE BLOCKS
---------------------------
Only words that are BOTH in the memo AND missing from this list can ever be blocked by provenance. So if a normal
memo word ("confidential", "management") were missing here, every query using it would be blocked. If a real
secret ("halyard") were in here, provenance would stop protecting it. When you change this list, run
`python3 -m checks.benign_run notes/BENIGN.md` again and report both numbers.

It is written by hand (no dependency) and is deliberately not huge: generic English plus deal/finance terms.
"""

STOPWORDS = frozenset("""
a about above after again against all am an and any are as at be because been before being below between both but
by can could did do does doing down during each few for from further had has have having he her here hers herself
him himself his how i if in into is it its itself just me more most my myself no nor not now of off on once only or
other our ours ourselves out over own same she should so some such than that the their theirs them themselves then
there these they this those through to too under until up very was we were what when where which while who whom
why will with would you your yours yourself yourselves also via per vs etc s t
""".split())

COMMON = frozenset("""
able account across act action actually add added after again age ago agree ahead air allow almost alone along
already although always among amount analysis analyst analysts annual another answer anyone anything appear apply
approach area areas around ask asked available average away back bad bank based basis became become begin behind
believe best better big bill board body book both bring build business buy call called came capital care career
carry case cases cash cause center central certain chair chance change changed changes charge check chief child
choice city claim class clear close closed come comes common community company companies compare complete
concern conference consider continue control cost costs could country course court cover create current customer
customers cut data date day days deal deals decade decide decision deep demand describe design detail details
develop development difference different director discuss do done door down draw during early east economic
economy effect effort either else end enough enter entire especially even evening event ever every evidence exactly
example executive expect experience explain eye face fact factor fail fall family far fast fear federal feel few
field figure figures file final finally financial find fine firm firms first five focus follow following food
force foreign form former forward four free friend front full fund funds future game general get give given go
goal good government great green ground group grow growing growth guy half hand happen hard head health hear help
high history hold home hope hour hours house however huge human idea identify image impact important include
including income increase indeed indicate indicative industry information inside instead interest interesting
international investment investor investors involve issue issues item job join keep key kind know knowledge land
language large last late later lead leader learn least leave left legal less let letter level life light like
likely line list listed little live local long look lose loss lot low main maintain major make manage management
manager many market markets matter may maybe mean measure media meet meeting member mention method middle mid might
million billion thousand mind minute miss model modern moment money month months more morning most move much must
name national nature near nearly necessary need needed needs network never new news next nice night none note
nothing notice number numbers occur offer office officer often oil old once one only open operation opportunity
option order organization others outside owner page paid pain paper part partner partners party pass past pay
people per percent perform performance perhaps period person personal phone pick picture piece place plan planned
planning plans plant play player point policy political poor popular population position positive possible power
practice prepare preparing present president pressure pretty prevent price prices private probably problem
process processor processors processing produce product production products professional program project property
provide public pull purpose push put quality question quickly quite race raise range rate rather reach read ready
real reality realize really reason receive recent recently record red reduce reflect region relate remain remember
report reports represent require research resource respond response rest result results return reveal revenue
revenues review rich right rise risk road rock role room rule run sale sales same save say scene school score
second section sector security see seek seem sell send senior sense series serious serve service services set
seven several share shares short should show side sign significant similar simple simply since single sister sit
site situation six size skill small social society some someone something sometimes soon sort source sources space
speak special specific spend staff stage stand standard start state statement states stay step still stock stocks
stop story strategy street strictly strong structure student study stuff style subject success successful such
suddenly suggest summer support sure surface system table take talk target task tax team tell ten tend term terms
test than thank that theory thing things think third those though thought three through throughout time today
together tonight top total tough toward town trade traditional training travel treat treatment tree trial trip
trouble true truth try turn two type under understand unit until upon us use used user usually value values various
very view visit voice vote wait walk wall want watch water way weapon wear week weeks weight well west whatever
whether while white whole why wide wife win wind window wish within without woman wonder word words work worker
world worry write writer wrong yard year years yes yet young
confidential confidentiality contact contacts strictly internal draft memo memorandum note notes ref reference
regarding re attn attention subject january february march april may june july august september october november
december monday tuesday wednesday thursday friday saturday sunday week weekend quarter q1 q2 q3 q4 fy ttm ltm ytd
acquisition acquisitions acquire acquired acquirer buyer buyers seller sellers target targets offer offers bid bids
merger mergers deal deals transaction transactions valuation valuations multiple multiples ev ebitda ebit revenue
revenues sales margin margins profit profits earnings eps equity debt leverage loan loans bond bonds credit
interest rate rates yield dividend dividends shareholder shareholders stake stakes premium discount price prices
priced pricing indicative binding nonbinding term sheet loi diligence due advisory adviser advisers advisor
advisors banker bankers fund funds private public listed unlisted ipo exchange nyse nasdaq lse ticker peer peers
comparable comparables comps sector sectors industry industries segment segments vertical market markets share
growth grow growing grew cagr yoy organic inorganic forecast forecasts outlook guidance estimate estimates
consensus analyst analysts report reports annual quarterly filing filings sec 10k 10q proxy investor investors
relations ir payments payment processing processor processors processed merchant merchants acquiring acquirer
issuer issuers card cards credit debit interchange fee fees take volume volumes tpv gpv fintech fintechs software
saas platform platforms gateway gateways wallet wallets checkout pos terminal terminals ecommerce commerce online
offline retail retailer retailers bank banks banking regulation regulatory compliance license licence licensing
money transmitter fraud chargeback chargebacks risk midmarket mid market enterprise smb small medium large company
companies corporation corp inc ltd llc plc group holdings holding partners partner capital management managing
manager managers director directors officer officers ceo cfo coo cto chairman board executive executives founder
founders team employees headcount staff meeting meetings management presentation call calls planned schedule
scheduled week weeks contact contacts needed need research question questions how fast
""".split())
