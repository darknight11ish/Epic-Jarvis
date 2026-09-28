"""jarvis_sky_places.py - the towns "Show the sun and moon behind the animal"
can find without going online (jarvis_sky.py reads DATA; nothing else does).

Data: GeoNames (https://www.geonames.org), licensed under Creative Commons
Attribution 4.0 (CC BY 4.0), through geonamescache 3.0.2 (MIT). Made by
tools/gen_sky_places.py - do not edit by hand. One town a line: name,
country code, region (a US state; empty elsewhere), latitude, longitude,
population, separated by tabs.
"""

DATA = """\
'Alī Ābād-e Katūl	IR		36.91	54.87	52838
's-Hertogenbosch	NL		51.70	5.30	160783
'Ākra	IQ		36.73	43.88	105370
'Ārdamatā	SD		13.48	22.49	55637
6th of October City	EG		29.82	31.05	368650
A Coruña	ES		43.37	-8.40	250438
Aachen	DE		50.78	6.08	265208
Aalborg	DK		57.05	9.92	142937
Aalen	DE		48.84	10.09	67085
Aalst	BE		50.94	4.04	77534
Aarsâl	LB		34.18	36.42	50000
Aba	NG		5.11	7.37	1160000
Abadan	IR		30.34	48.30	231476
Abadeh	IR		31.16	52.65	59116
Abaetetuba	BR		-1.72	-48.88	158188
Abakaliki	NG		6.32	8.11	134102
Abakan	RU		53.72	91.43	184168
Abancay	PE		-13.63	-72.88	72277
Abbey Wood	GB		51.49	0.11	17700
Abbotsford	CA		49.06	-122.25	141397
Abbottabad	PK		34.15	73.21	275890
Abengourou	CI		6.73	-3.50	130810
Abeokuta	NG		7.16	3.35	735000
Abepura	ID		-2.60	140.63	62248
Aberdare	GB		51.71	-3.45	31135
Aberdeen	GB		57.14	-2.10	198590
Aberdeen	HK		22.25	114.15	157400
Aberdeen	US	South Dakota	45.46	-98.49	28102
Aberdeen	US	Washington	46.98	-123.82	16276
Aberdeen	US	Maryland	39.51	-76.16	15580
Aberystwyth	GB		52.42	-4.08	18749
Abha	SA		18.22	42.51	210886
Abhar	IR		36.15	49.22	69889
Abidjan	CI		5.35	-4.00	6321017
Abiko	JP		35.87	140.02	131771
Abilene	US	Texas	32.45	-99.73	125182
Abingdon	GB		51.67	-1.28	38676
Abington	US	Pennsylvania	40.12	-75.12	55310
Abington	US	Massachusetts	42.10	-70.95	15985
Abnūb	EG		27.27	31.15	111785
Abobo	CI		5.42	-4.02	1340083
Abohar	IN		30.14	74.20	145302
Aboisso	CI		5.47	-3.21	59225
Abomey	BJ		7.18	1.99	117824
Abomey-Calavi	BJ		6.45	2.36	385755
Abovyan	AM		40.27	44.63	50556
Abreu e Lima	BR		-7.91	-34.90	103945
Abu Dhabi	AE		24.45	54.40	1807000
Abuja	NG		9.06	7.50	2690000
Abéché	TD		13.83	20.83	139983
Abū al Maţāmīr	EG		30.91	30.17	66946
Abū al-Kahṣīb	IQ		30.44	47.88	357771
Abū an Numrus	EG		29.95	31.20	86601
Abū Ghurayb	IQ		33.31	44.18	900000
Abū Kabīr	EG		30.73	31.67	154466
Abū Qurqāş	EG		27.93	30.84	90266
Abū Tīj	EG		27.05	31.32	105418
Abū Ḩummuş	EG		31.09	30.31	61388
Abū ‘Arīsh	SA		16.97	42.83	69632
Acapulco de Juárez	MX		16.85	-99.91	658609
Acaraú	BR		-2.89	-40.12	65264
Acarigua	VE		9.55	-69.20	188278
Acará	BR		-1.96	-48.20	59023
Acayucan	MX		17.95	-94.91	50934
Accra	GH		5.56	-0.20	1963264
Accrington	GB		53.75	-2.36	34897
Acerra	IT		40.94	14.37	59910
Achalpur	IN		21.26	77.51	112311
Acharnés	GR		38.08	23.73	99346
Acheng	CN		45.55	126.95	144665
Achinsk	RU		56.27	90.50	117634
Acilia-Castel Fusano-Ostia Antica	IT		41.76	12.33	129362
Acocks Green	GB		52.45	-1.82	26635
Acre	IL		32.93	35.08	51420
Acton	GB		51.51	-0.28	62480
Acton	US	Massachusetts	42.49	-71.43	20897
Acworth	US	Georgia	34.07	-84.68	22131
Acámbaro	MX		20.03	-100.72	57972
Ad Darwa	MA		33.37	-7.54	52108
Ad Dawādimī	SA		24.51	44.39	86861
Ad Dilinjāt	EG		30.83	30.54	68901
Ad Dir‘īyah	SA		24.75	46.54	61609
Ad Douiem	SD		14.00	32.31	87068
Ad-Damazin	SD		11.79	34.36	186051
Ad-Damir	SD		17.60	33.97	103941
Ada	US	Oklahoma	34.77	-96.68	17303
Adachi	JP		35.76	139.81	695043
Adams Morgan	US	District of Columbia	38.92	-77.04	15830
Adamstown	PN		-25.07	-130.10	46
Adana	TR		36.99	35.33	1816750
Adapazarı	TR		40.78	30.40	286787
Addis Ababa	ET		9.02	38.75	3860000
Addison	US	Illinois	41.93	-87.99	37208
Addison	US	Texas	32.96	-96.83	15518
Adelaide	AU		-34.93	138.60	1469163
Adelaide city centre	AU		-34.93	138.60	19820
Adelaide Hills	AU		-34.91	138.71	72260
Adelanto	US	California	34.58	-117.41	33166
Adelphi	US	Maryland	39.00	-76.97	15086
Aden	YE		12.78	45.04	1079670
Adenta	GH		5.71	-0.15	50652
Adilcevaz	TR		38.80	42.73	52781
Adiwerna	ID		-6.94	109.13	134188
Adler	RU		43.43	39.92	70200
Admiralteisky	RU		59.92	30.30	157897
Ado-Ekiti	NG		7.62	5.22	435000
Adoni	IN		15.63	77.27	184625
Adrar	DZ		27.87	-0.29	68276
Adrian	US	Michigan	41.90	-84.04	20691
Adwa	ET		14.16	38.90	85600
Adwick le Street	GB		53.57	-1.18	19481
Adzopé	CI		6.11	-3.86	76122
Adıyaman	TR		37.76	38.28	290883
Affton	US	Missouri	38.55	-90.33	20307
Afgooye	SO		2.14	45.12	65461
Afikpo	NG		5.89	7.94	71866
Aflao	GH		6.12	1.19	66546
Aflou	DZ		34.11	2.10	93585
Afragola	IT		40.92	14.31	64470
Afyonkarahisar	TR		38.76	30.54	251799
Agadez	NE		16.97	7.99	149549
Agadir	MA		30.42	-9.60	698310
Agartala	IN		23.84	91.28	400004
Agawam	US	Massachusetts	42.07	-72.61	28761
Agbor	NG		6.25	6.19	67610
Agboville	CI		5.93	-4.21	81770
Agege	NG		6.62	3.33	683600
Ageo	JP		35.97	139.61	226940
Agincourt North	CA		43.80	-79.28	29113
Agincourt South-Malvern West	CA		43.79	-79.27	23757
Agios Dimitrios	GR		37.93	23.73	71294
Agnibilékrou	CI		7.13	-3.20	63015
Agoura	US	California	34.14	-118.74	20537
Agoura Hills	US	California	34.14	-118.77	20915
Agra	IN		27.18	78.02	1430055
Agua Caliente	US	California	38.32	-122.49	27090
Agua Prieta	MX		31.32	-109.54	77254
Agua Rasa	BR		-23.57	-46.57	85788
Aguachica	CO		8.31	-73.62	97525
Aguascalientes	MX		21.88	-102.28	722250
Agulu	NG		6.10	7.06	79021
Agustín Codazzi	CO		10.04	-73.24	51478
Agía Paraskeví	GR		38.02	23.83	59704
Ahar	IR		38.48	47.07	100641
Ahilyanagar	IN		19.09	74.74	367140
Ahlat	TR		38.75	42.48	64695
Ahlen	DE		51.76	7.89	55280
Ahmadpur East	PK		29.14	71.26	196718
Ahmedabad	IN		23.03	72.59	6357693
Ahu	CN		34.38	118.60	55298
Ahuntsic-Cartierville	CA		45.57	-73.67	135336
Ahvaz	IR		31.32	48.68	841145
Ahwatukee Foothills	US	Arizona	33.34	-111.98	83464
Aigáleo	GR		37.98	23.68	69946
Aihara	JP		35.60	139.32	725493
Aihui	CN		49.98	127.48	192764
Aiken	US	South Carolina	33.56	-81.72	30604
Ain El Aouda	MA		33.80	-6.79	54397
Aira	JP		31.77	130.59	76348
Airdrie	CA		51.30	-114.04	90044
Airdrie	GB		55.87	-3.98	36390
Airoli	IN		19.15	73.00	100000
Airport	US	Hawaii	21.34	-157.93	28916
Aisai	JP		35.16	136.73	60829
Ait Melloul	MA		30.34	-9.50	187652
Aix-en-Provence	FR		43.53	5.45	146821
Aizawl	IN		23.73	92.72	293416
Aizu-Wakamatsu	JP		37.49	139.95	118159
Ajaccio	FR		41.92	8.74	54364
Ajapnyak	AM		40.20	44.47	122800
Ajax	CA		43.85	-79.03	119677
Ajdabiya	LY		30.76	20.23	131773
Ajegunle	NG		6.45	3.33	550000
Ajman	AE		25.40	55.48	490035
Ajmer	IN		26.45	74.64	542321
Akademgorodok	RU		54.85	83.11	50000
Akademicheskoe	RU		60.01	30.39	103304
Akashi	JP		34.66	135.01	303601
Aketi	CD		2.74	23.78	61437
Akhisar	TR		38.92	27.84	84659
Akhmīm	EG		26.56	31.75	151430
Akihabara	JP		35.70	139.77	77200
Akim Oda	GH		5.93	-0.99	60604
Akiruno	JP		35.73	139.23	81912
Akishima	JP		35.72	139.38	113949
Akita	JP		39.72	140.12	307672
Akola	IN		20.71	77.00	428857
Akot	IN		21.10	77.06	92637
Akowonjo	NG		6.61	3.31	308900
Akron	US	Ohio	41.08	-81.52	197542
Aksaray	TR		38.37	34.03	327575
Aksum	ET		14.12	38.72	94500
Aktau	KZ		43.66	51.17	147443
Aktobe	KZ		50.28	57.21	500757
Aku	NG		6.71	7.32	73742
Akure	NG		7.25	5.19	730000
Akçapınar	TR		38.95	38.94	84366
Akşehir	TR		38.36	31.42	64446
Al Aaroui	MA		35.01	-3.01	51976
Al Ain City	AE		24.19	55.76	846747
Al Ajaylat	LY		32.76	12.38	130546
Al Aḩmadī	KW		29.08	48.08	637411
Al Badrashayn	EG		29.85	31.27	90833
Al Badārī	EG		26.99	31.42	56033
Al Bahah	SA		20.01	41.47	88419
Al Balyanā	EG		26.24	32.00	68413
Al Bayḑā’	LY		32.76	21.76	129439
Al Başrah al Qadīmah	IQ		30.50	47.82	2015483
Al Buraymī	OM		24.25	55.79	73670
Al Burj	EG		31.58	30.98	60320
Al Bāb	SY		36.37	37.52	130745
Al Bājūr	EG		30.43	31.04	62961
Al Diwaniyah	IQ		31.99	44.93	318801
Al Fallūjah	IQ		33.35	43.79	190159
Al Farwānīyah	KW		29.28	47.96	86525
Al Fashn	EG		28.82	30.90	112999
Al Fayyum	EG		29.31	30.84	519047
Al Faḩāḩīl	KW		29.08	48.13	68290
Al Fqih Ben Çalah	MA		32.50	-6.69	111402
Al Fāw	IQ		29.97	48.47	104569
Al Ghanāyim	EG		26.88	31.33	70884
Al Hillah	IQ		32.46	44.42	455700
Al Hindīyah	IQ		32.54	44.22	139578
Al Hoceïma	MA		35.25	-3.94	395644
Al Hufūf	SA		25.36	49.59	293179
Al Hārithah	IQ		30.58	47.76	92395
Al Ibrāhīmīyah	EG		30.72	31.56	53791
Al Jadīd	LY		27.05	14.40	126386
Al Jammālīyah	EG		31.18	31.86	99641
Al Jubayl	SA		27.02	49.62	237274
Al Jumayl	LY		32.85	12.06	102000
Al Karama	AE		25.24	55.30	75560
Al Khafjī	SA		28.44	48.49	54857
Al Kharj	SA		24.16	47.33	425300
Al Khums	LY		32.65	14.26	201943
Al Khuşūş	EG		30.15	31.32	488904
Al Khābūrah	OM		23.97	57.09	50223
Al Khānkah	EG		30.21	31.37	81646
Al Khārjah	EG		25.45	30.55	83108
Al Līth	SA		20.15	40.27	72000
Al Madīnah	IQ		30.96	47.27	255000
Al Majaz	AE		25.32	55.39	116503
Al Mansurah	EG		31.04	31.38	621953
Al Manzalah	EG		31.16	31.94	127394
Al Manāqil	SD		14.25	32.99	128297
Al Manşūrah	QA		25.27	51.53	65493
Al Marj	LY		32.49	20.83	85315
Al Marāghah	EG		26.70	31.60	53643
Al Mawşil al Jadīdah	IQ		36.33	43.11	2065597
Al Mayādīn	SY		35.02	40.45	54534
Al Maţarīyah	EG		31.18	32.03	162045
Al Maţār al ‘Atīq	QA		25.25	51.56	76774
Al Maḩallah al Kubrá	EG		30.97	31.17	592573
Al Maḩmūdīyah	IQ		33.06	44.37	350000
Al Minshāh	EG		26.48	31.80	91149
Al Miqdādīyah	IQ		33.98	44.94	155968
Al Mubarraz	SA		25.41	49.59	290802
Al Muharraq	BH		26.26	50.61	176583
Al Qadarif	SD		14.03	35.38	363945
Al Qanāyāt	EG		30.62	31.46	70687
Al Qanāţir al Khayrīyah	EG		30.19	31.14	83568
Al Qaţīf	SA		26.57	50.01	98259
Al Qurayn	EG		30.62	31.74	94632
Al Qurnah	IQ		31.02	47.43	134174
Al Qāhirah al Jadīdah	EG		30.04	31.44	313139
Al Qāmishlī	SY		37.05	41.23	184231
Al Qā’im	IQ		34.39	40.99	74100
Al Qūşīyah	EG		27.44	30.82	99598
Al Sajaah	AE		25.32	55.63	53079
Al Shamkhah City	AE		24.39	54.71	61710
Al Warqaa	AE		25.19	55.42	59111
Al Wāsiţah	EG		29.34	31.21	57870
Al Ḩasakah	SY		36.50	40.75	422445
Al Ḩawāmidīyah	EG		29.90	31.25	155055
Al Ḩayy	IQ		32.17	46.04	78272
Al Ḩudaydah	YE		14.80	42.95	734699
Al Ḩurshah	LY		32.76	12.67	81119
Al Ḩusaynīyah	EG		30.86	31.92	50651
Al Ḩāmūl	EG		31.31	31.15	58430
Al ‘Amārah	IQ		31.84	47.14	323302
Al ‘Azīzīyah	LY		32.53	13.02	52404
Al ‘Āshir min Ramaḑān	EG		30.30	31.75	246148
Al-'Ubūr	EG		30.23	31.48	138987
Al-Hamdaniya	IQ		36.27	43.38	50000
Al-Junaynah	SD		13.45	22.45	162981
Al-Khārijah	EG		25.25	30.55	83108
Al-Kut	IQ		32.51	45.82	315162
Al-Musayab	IQ		32.78	44.29	101873
Al-Qāsim	IQ		32.30	44.68	93546
Al-Tabqa	SY		35.84	38.55	87880
al-Yarmūk	SY		33.47	36.30	99999
Ala Moana - Kakaʻako	US	Hawaii	21.30	-157.86	18957
Alabaster	US	Alabama	33.24	-86.82	32707
Alabel	PH		6.10	125.29	90120
Alafaya	US	Florida	28.56	-81.21	78113
Alaghsas	NE		17.02	8.02	88561
Alagoinhas	BR		-12.14	-38.42	122688
Alahabad	PK		30.88	74.06	80084
Alamar	CU		23.16	-82.28	100000
Alamata	ET		12.42	39.56	70400
Alameda	US	California	37.77	-122.26	78630
Alamo	US	Texas	26.18	-98.12	19246
Alamogordo	US	New Mexico	32.90	-105.96	30753
Alandur	IN		13.00	80.21	164430
Alanya	TR		36.54	32.00	364180
Alappuzha	IN		9.49	76.33	240991
Alasia	NG		6.47	3.17	100000
Alba Iulia	RO		46.07	23.58	64227
Albacete	ES		38.99	-1.86	173050
Albany	US	New York	42.65	-73.76	101228
Albany	US	Georgia	31.58	-84.16	74843
Albany	US	Oregon	44.64	-123.11	52175
Albany	AU		-35.03	117.88	35053
Albany	US	California	37.89	-122.30	19735
Albany Creek	AU		-27.35	152.97	15532
Albany Park	US	Illinois	41.97	-87.72	52079
Albemarle	US	North Carolina	35.35	-80.20	16003
Albert Lea	US	Minnesota	43.65	-93.37	17674
Alberton	ZA		-26.27	28.12	121536
Albertville	US	Alabama	34.27	-86.21	21462
Albi	FR		43.93	2.15	52409
Albuquerque	US	New Mexico	35.08	-106.65	564559
Alcalá de Guadaira	ES		37.34	-5.84	70155
Alcalá de Henares	ES		40.48	-3.36	193751
Alchevsk	UA		48.47	38.80	106062
Alcobendas	ES		40.55	-3.64	116037
Alcorcón	ES		40.35	-3.82	172384
Alcoy	ES		38.71	-0.47	61552
Aldershot	GB		51.25	-0.76	40160
Aldine	US	Texas	29.93	-95.38	15869
Aldridge	GB		52.61	-1.92	26896
Alegrete	BR		-29.78	-55.79	72409
Aleksandrov	RU		56.40	38.71	64088
Alekseyevka	RU		55.63	37.80	78000
Aleksin	RU		54.50	37.07	66885
Alenquer	BR		-1.94	-54.74	69377
Aleppo	SY		36.20	37.16	2098210
Alessandria	IT		44.91	8.61	92104
Alexandra	ZA		-26.11	28.10	179624
Alexandra Hills	AU		-27.53	153.23	16043
Alexandria	EG		31.20	29.92	5263542
Alexandria	US	Virginia	38.80	-77.05	159467
Alexandria	US	Louisiana	31.31	-92.45	47889
Alexandroupoli	GR		40.85	25.88	52979
Aley	LB		33.81	35.60	130000
Alfenas	BR		-21.43	-45.95	78970
Alfreton	GB		53.10	-1.38	22550
Algeciras	ES		36.13	-5.45	121414
Algiers	DZ		36.73	3.09	2364230
Algonquin	US	Illinois	42.17	-88.29	30571
Algorta	ES		43.35	-3.01	82624
Algueirão	PT		38.80	-9.34	66250
Alhambra	US	Arizona	33.50	-112.13	127764
Alhambra	US	California	34.10	-118.13	85551
Ali Mendjeli	DZ		36.25	6.57	64120
Ali Sabih	DJ		11.16	42.71	50006
Aliamanu / Salt Lakes / Foster Village	US	Hawaii	21.36	-157.92	38833
Aliayabiagba	NG		6.45	3.33	228000
Alicante	ES		38.35	-0.48	348901
Alice	US	Texas	27.75	-98.07	19408
Alice Springs	AU		-23.70	133.88	25912
Alicia	PH		16.78	121.70	74699
Alief	US	Texas	29.71	-95.60	98725
Alimosho	NG		6.61	3.30	308290
Aliso Viejo	US	California	33.57	-117.73	50195
Alkmaar	NL		52.63	4.75	94853
Allapattah	US	Florida	25.81	-80.22	54289
Allen	US	Texas	33.10	-96.67	98143
Allen Park	US	Michigan	42.26	-83.21	27425
Allendale	US	Michigan	42.97	-85.95	17579
Allentown	US	Pennsylvania	40.61	-75.49	120207
Allerton	GB		53.37	-2.89	15540
Alliance	US	Ohio	40.92	-81.11	22055
Allinagaram	IN		10.03	77.48	94453
Allison Park	US	Pennsylvania	40.56	-79.96	21552
Alliston	CA		44.15	-79.87	18809
Alloa	GB		56.12	-3.79	20390
Allston	US	Massachusetts	42.36	-71.13	28821
Alma	CA		48.55	-71.65	29526
Almaty	KZ		43.25	76.91	1977011
Almelo	NL		52.36	6.66	72725
Almendares	CU		23.11	-82.42	240000
Almere Stad	NL		52.37	5.21	176432
Almería	ES		36.84	-2.46	196851
Almirante Tamandaré	BR		-25.32	-49.31	119825
Alofi	NU		-19.05	-169.92	624
Aloha	US	Oregon	45.49	-122.87	49425
Alor Setar	MY		6.12	100.36	417800
Alpharetta	US	Georgia	34.08	-84.29	63693
Alphen aan den Rijn	NL		52.13	4.66	70251
Alsip	US	Illinois	41.67	-87.74	19346
Alt-Hohenschönhausen	DE		52.55	13.50	50070
Alta Vista	CA		45.39	-75.66	24726
Altadena	US	California	34.19	-118.13	42777
Altagracia de Orituco	VE		9.86	-66.38	68207
Altamira	BR		-3.20	-52.21	126279
Altamira	MX		22.39	-97.94	59536
Altamont	US	Oregon	42.21	-121.74	19257
Altamonte Springs	US	Florida	28.66	-81.37	43159
Altamura	IT		40.83	16.55	70539
Alto Barinas	VE		8.59	-70.23	284289
Alto Hospicio	CL		-20.27	-70.10	142086
Alton	US	Illinois	38.89	-90.18	27003
Alton	GB		51.15	-0.97	19425
Alton	US	Texas	26.29	-98.31	15760
Altona	DE		53.55	9.93	250192
Altona Meadows	AU		-37.88	144.78	18479
Altoona	US	Pennsylvania	40.52	-78.39	45344
Altoona	US	Iowa	41.64	-93.46	16984
Altrincham	GB		53.39	-2.35	49680
Altuf’yevskiy	RU		55.88	37.58	54000
Altus	US	Oklahoma	34.64	-99.33	19214
Aluche	ES		40.39	-3.76	66588
Alum Rock	US	California	37.37	-121.83	15536
Alvand	IR		36.19	50.06	90000
Alvin	US	Texas	29.42	-95.24	25791
Alvorada	BR		-30.00	-51.08	187315
Alwar	IN		27.56	76.62	322568
Alīgarh	IN		27.88	78.07	753207
Alīgūdarz	IR		33.40	49.69	89268
Alīpur Duār	IN		26.48	89.52	65232
Al’met’yevsk	RU		54.90	52.32	140437
Am Timan	TD		11.04	20.28	74691
Ama	JP		35.18	136.80	86126
Amadora	PT		38.75	-9.23	178858
Amagasaki	JP		34.72	135.42	459593
Amahai	ID		-3.34	128.92	50478
Amaigbo	NG		5.79	7.84	127300
Amakusa	JP		32.46	130.19	83082
Amalner	IN		21.04	75.06	97369
Amalāpuram	IN		16.58	82.01	53231
Amanfrom	GH		5.54	-0.40	119467
Amarapura	MM		21.91	96.05	237618
Amaravati	IN		16.51	80.52	103000
Amarillo	US	Texas	35.22	-101.83	198645
Amasya	TR		40.65	35.83	114921
Amatitlán	GT		14.48	-90.63	71836
Ambala Sadar	IN		30.34	76.86	104974
Ambalangoda	LK		6.24	80.05	56783
Ambalantota	LK		6.12	81.02	80506
Ambanja	MG		-13.67	48.45	63884
Ambarawa	ID		-7.26	110.40	65096
Ambarnath	IN		19.20	73.17	253475
Ambato	EC		-1.25	-78.62	387309
Ambatondrazaka	MG		-17.83	48.42	50463
Ambattur	IN		13.10	80.16	466205
Ambikāpur	IN		23.12	83.20	121071
Ambilobe	MG		-13.20	49.05	66029
Ambon	ID		-3.70	128.18	347288
Ambovombe	MG		-25.18	46.09	69265
Ambur	IN		12.79	78.72	114608
Ambājogāi	IN		18.73	76.39	74114
Ambāla	IN		30.36	76.80	195153
American Canyon	US	California	38.17	-122.26	20554
American Fork	US	Utah	40.38	-111.80	28326
Americana	BR		-22.74	-47.33	246655
Americus	US	Georgia	32.07	-84.23	16028
Amersfoort	NL		52.16	5.39	139914
Amersham	GB		51.67	-0.62	21731
Amersham on the Hill	GB		51.67	-0.61	17719
Ames	US	Iowa	42.03	-93.62	65060
Amesbury	US	Massachusetts	42.86	-70.93	18313
Amherst	US	New York	42.98	-78.80	122366
Amherst	US	Massachusetts	42.37	-72.52	39833
Amherst Center	US	Massachusetts	42.38	-72.52	19065
Amiens	FR		49.90	2.30	143086
Amman	JO		31.96	35.95	1275857
Ammanford	GB		51.79	-3.99	23709
Amora	PT		38.63	-9.12	52577
Amos	CA		48.57	-78.12	17918
Amozoc de Mota	MX		19.05	-98.05	95322
Ampang	MY		3.15	101.77	126285
Amparo	BR		-22.70	-46.76	72677
Ampthill	GB		52.03	-0.50	20026
Amravati	IN		20.93	77.75	647057
Amreli	IN		21.60	71.21	117967
Amritsar	IN		31.62	74.88	1159227
Amroha	IN		28.90	78.47	176253
Amstelveen	NL		52.30	4.86	79639
Amsterdam	NL		52.37	4.89	741636
Amsterdam	US	New York	42.94	-74.19	18008
Amsterdam-Zuidoost	NL		52.31	4.97	84811
Amuntai	ID		-2.42	115.25	55560
An Hải	VN		16.07	108.23	82635
An Khê	VN		13.95	108.65	81600
An Muileann gCearr	IE		53.52	-7.34	22667
An Nhơn	VN		13.89	109.11	308396
An Nuhūd	SD		12.70	28.43	108008
An Nu‘mānīyah	IQ		32.56	45.41	110000
Anaco	VE		9.43	-64.46	139397
Anacortes	US	Washington	48.51	-122.61	18103
Anaheim	US	California	33.84	-117.91	350742
Anakapalle	IN		17.69	83.00	86519
Anamur	TR		36.08	32.84	57128
Anan	JP		33.92	134.65	70285
Anand	IN		22.55	72.96	209410
Ananindeua	BR		-1.37	-48.37	433956
Anantapur	IN		14.68	77.61	267161
Anantnag	IN		33.73	75.15	150592
Anapa	RU		44.89	37.32	53600
Anbu	CN		23.45	116.68	162964
Ancaster	CA		43.22	-79.99	40557
Anchorage	US	Alaska	61.22	-149.90	289600
Ancona	IT		43.61	13.51	89994
Anda	CN		46.45	125.30	181271
Anderlecht	BE		50.84	4.31	160553
Anderson	US	Indiana	40.11	-85.68	55305
Anderson	US	South Carolina	34.50	-82.65	27335
Andijon	UZ		40.78	72.35	747800
Andong	KR		36.57	128.72	153348
Andorra la Vella	AD		42.51	1.52	20430
Andover	GB		51.21	-1.49	42276
Andover	US	Minnesota	45.23	-93.29	32213
Andradina	BR		-20.90	-51.38	61473
Andria	IT		41.23	16.30	99784
Andulo	AO		-11.49	16.70	50000
Andīmeshk	IR		32.46	48.35	135116
Andīsheh	IR		35.75	51.28	116062
Ang Mo Kio New Town	SG		1.38	103.84	159340
Angarsk	RU		52.56	103.91	243158
Angat	PH		14.93	121.03	67862
Angeles City	PH		15.15	120.58	483452
Angers	FR		47.47	-0.55	168279
Angleton	US	Texas	29.17	-95.43	19429
Angoche	MZ		-16.23	39.91	104540
Angono	PH		14.53	121.15	134975
Angra dos Reis	BR		-23.01	-44.32	179120
Angren	UZ		41.02	70.14	191300
Anguo	CN		34.83	116.82	82181
Angyalföld	HU		47.55	19.08	62006
Anhanguera	BR		-23.43	-46.79	75360
Anjangaon	IN		21.17	77.31	56380
Anjiang	CN		27.32	110.10	55421
Anju	KP		39.62	125.66	50196
Anjār	IN		23.11	70.03	87183
Anjō	JP		34.96	137.08	188693
Ankang	CN		32.68	109.02	870126
Ankara	TR		39.92	32.85	3517182
Ankeny	US	Iowa	41.73	-93.61	56764
Ankleshwar	IN		21.63	72.99	89457
Anliu	CN		23.70	115.68	115560
Anlong	CN		25.10	105.52	86416
Anlong Veaeng	KH		14.23	104.08	56927
Anlu	CN		31.26	113.68	71198
Ann	MM		19.80	94.05	119714
Ann Arbor	US	Michigan	42.28	-83.74	117070
Annaba	DZ		36.90	7.77	342703
Annaka	JP		36.33	138.90	57013
Annandale	US	Virginia	38.83	-77.20	41008
Annapolis	US	Maryland	38.98	-76.49	40812
Annex	CA		43.67	-79.40	30526
Anning	CN		24.92	102.48	106795
Anniston	US	Alabama	33.66	-85.83	22347
Anoka	US	Minnesota	45.20	-93.39	17350
Anqing	CN		30.51	117.05	804493
Anqiu	CN		36.43	119.19	364208
Ansan-si	KR		37.32	126.82	623256
Anseong	KR		37.01	127.27	69255
Anshan	CN		41.12	122.99	1450000
Anshun	CN		26.25	105.93	765313
Ansonia	US	Connecticut	41.35	-73.08	18854
Antakya	TR		36.21	36.16	399045
Antalaha	MG		-14.90	50.28	71898
Antalya	TR		36.91	30.70	1335002
Antananarivo	MG		-18.91	47.54	1349501
Antanifotsy	MG		-19.65	47.32	70626
Antelope	US	California	38.71	-121.33	45770
Anthem	US	Arizona	33.87	-112.15	21700
Antibes	FR		43.58	7.12	76393
Antioch	US	California	38.00	-121.81	110542
Antipolo	PH		14.63	121.12	913712
Antofagasta	CL		-23.65	-70.40	401096
Antony	FR		48.75	2.30	59845
Antratsyt	UA		48.12	39.09	52150
Antrim	GB		54.72	-6.21	19661
Antsalova	MG		-18.67	44.62	58280
Antsirabe	MG		-19.87	47.03	260907
Antsiranana	MG		-12.32	49.29	136959
Antu	CN		43.10	128.91	58872
Antwerp	BE		51.22	4.40	529247
Anuradhapura	LK		8.31	80.41	60943
Anusawari	TH		13.89	100.61	94550
Anyama	CI		5.49	-4.05	133905
Anyang	CN		36.10	114.38	1146839
Anyang-si	KR		37.39	126.93	595644
Anzhero-Sudzhensk	RU		56.08	86.02	82526
Anápolis	BR		-16.33	-48.95	319587
Aomori	JP		40.82	140.73	298394
Aonla	IN		28.27	79.17	50011
Aoxi	CN		27.43	115.84	82717
Apac	UG		1.98	32.54	67700
Apache Junction	US	Arizona	33.42	-111.55	38074
Apalit	PH		14.95	120.77	121057
Aparecida de Goiânia	BR		-16.82	-49.24	510770
Aparri	PH		18.36	121.64	68368
Apartadó	CO		7.88	-76.63	86438
Apatity	RU		67.58	33.41	61186
Apatzingán	MX		19.09	-102.36	102362
Apeldoorn	NL		52.21	5.97	136670
Apex	US	North Carolina	35.73	-78.85	45585
Apia	WS		-13.83	-171.77	40407
Apomu	NG		7.35	4.18	71656
Apopa	SV		13.81	-89.18	112158
Apopka	US	Florida	28.68	-81.51	48382
Apple Valley	US	California	34.50	-117.19	72174
Apple Valley	US	Minnesota	44.73	-93.22	51221
Appleton	US	Wisconsin	44.26	-88.42	74139
Aprilia	IT		41.59	12.65	74977
Apucarana	BR		-23.55	-51.46	130134
Aqaba	JO		29.53	35.01	95048
Aqsu	CN		41.18	80.28	535657
Aquiraz	BR		-3.90	-38.39	65116
Ar Ramthā	JO		32.56	36.01	155693
Ar Raqqah	SY		35.95	39.01	531952
Ar Rass	SA		25.87	43.50	81728
Ar Rastan	SY		34.93	36.73	53152
Ar Rayyān	QA		25.29	51.42	272465
Ar Rifā‘	BH		26.13	50.55	115495
Ar Riqqah	KW		29.15	48.09	52068
Ar Rumaylah	AE		25.40	55.43	86000
Ar Rumaythīyah	KW		29.31	48.07	58135
Ara Damansara	MY		3.12	101.59	60000
Arabkir	AM		40.21	44.50	119300
Aracaju	BR		-10.91	-37.07	664908
Aracruz	BR		-19.82	-40.27	94765
Arad	RO		46.18	21.32	169065
Araguari	BR		-18.65	-48.19	117808
Araguaína	BR		-7.19	-48.21	105019
Arakawa	JP		35.74	139.78	216900
Arakkonam	IN		13.08	79.67	79080
Aramoko-Ekiti	NG		7.70	5.04	74491
Arandas	MX		20.71	-102.35	52175
Aranjuez	ES		40.03	-3.60	54055
Arao	JP		32.98	130.45	53675
Arapiraca	BR		-9.75	-36.66	243661
Arapongas	BR		-23.42	-51.42	119138
Arar	SA		30.98	41.04	148540
Araranguá	BR		-28.94	-49.50	71922
Araraquara	BR		-21.79	-48.18	168468
Araras	BR		-22.36	-47.38	135331
Araripina	BR		-7.58	-40.50	90104
Araruama	BR		-22.87	-42.34	137773
Arashiyama	JP		35.01	135.68	50000
Arauca	CO		7.08	-70.76	85585
Araucária	BR		-25.59	-49.41	151666
Araure	VE		9.58	-69.24	181820
Araxá	BR		-19.59	-46.94	111691
Arayat	PH		15.15	120.77	87987
Araçatuba	BR		-21.21	-50.43	170024
Arba Minch	ET		6.03	37.55	201000
Arbroath	GB		56.56	-2.59	23640
Arbutus	US	Maryland	39.25	-76.70	20483
Arbutus Ridge	CA		49.25	-123.17	15295
Arcadia	US	California	34.14	-118.04	58408
Arcahaie	HT		18.77	-72.51	130306
Arcata	US	California	40.87	-124.08	17843
Archway	GB		51.57	-0.13	215667
Arcola East	CA		50.43	-104.54	33725
Arcot	IN		12.91	79.32	55955
Arcoverde	BR		-8.42	-37.05	82003
Ardabīl	IR		38.25	48.29	410753
Ardakān	IR		32.31	54.02	58834
Arden-Arcade	US	California	38.60	-121.38	92186
Ardeşen	TR		41.19	40.98	67965
Ardmore	US	Oklahoma	34.17	-97.14	25176
Arecibo	PR		18.47	-66.72	87754
Arenella	IT		40.86	14.22	67634
Arequipa	PE		-16.40	-71.54	1195700
Arezzo	IT		43.46	11.88	100734
Arganda	ES		40.30	-3.44	51489
Arganzuela	ES		40.40	-3.70	148797
Argenteuil	FR		48.95	2.25	101475
Arica	CL		-18.48	-70.30	241653
Aricanduva	BR		-23.57	-46.52	89574
Arif Wala	PK		26.32	66.30	157063
Arifwala	PK		30.29	73.07	854462
Ariquemes	BR		-9.91	-63.04	96833
Arjawinangun	ID		-6.65	108.41	105845
Arjona	CO		10.25	-75.34	50405
Arkhangel’sk	RU		64.55	40.55	349742
Arles	FR		43.68	4.63	53431
Arlington	US	Texas	32.74	-97.11	388125
Arlington	US	Virginia	38.88	-77.10	207627
Arlington	US	Massachusetts	42.42	-71.16	42844
Arlington	US	Washington	48.20	-122.13	18949
Arlington Heights	US	Illinois	42.09	-87.98	75926
Arlit	NE		18.74	7.39	106448
Armant	EG		25.62	32.54	78695
Armavir	RU		45.00	41.11	199548
Armdale	CA		44.64	-63.63	16502
Armenia	CO		4.54	-75.67	304314
Armidale	AU		-30.50	151.67	21312
Arnavutköy	TR		41.18	28.74	198165
Arnhem	NL		51.98	5.91	162424
Arni	IN		12.67	79.29	63671
Arnold	GB		53.00	-1.13	37873
Arnold	US	Maryland	39.03	-76.50	23106
Arnold	US	Missouri	38.43	-90.38	21357
Arnsberg	DE		51.38	8.08	74879
Arona	ES		28.10	-16.68	78614
Arrah	IN		25.56	84.66	261430
Arraiján	PA		8.94	-79.64	76815
Arrecife	ES		28.96	-13.55	61351
Arroyo Grande	US	California	35.12	-120.59	18108
Arroyo Naranjo	CU		23.04	-82.38	210053
Arsen’yev	RU		44.16	133.27	58700
Arsi Negele	ET		7.35	38.67	98100
Arsikere	IN		13.31	76.26	53216
Arsuz	TR		36.41	35.89	109550
Artemisa	CU		22.81	-82.76	68073
Artesia	US	California	33.87	-118.08	16961
Artur Alvim	BR		-23.54	-46.49	104864
Artur Nogueira	BR		-22.57	-47.17	53157
Artux	CN		39.71	76.18	285000
Artëm	RU		43.36	132.19	102300
Arua	UG		3.02	30.91	72400
Arujá	BR		-23.40	-46.32	91157
Aruppukkottai	IN		9.51	78.10	87722
Arusha	TZ		-3.37	36.68	617631
Arvada	US	Colorado	39.80	-105.09	115368
Arvin	US	California	35.21	-118.83	20876
Arwal	IN		25.24	84.67	51849
Aryanah	TN		36.86	10.19	114486
Arzamas	RU		55.40	43.84	109479
Arzew	DZ		35.85	-0.32	58162
Arāk	IR		34.09	49.70	503647
Arāmbāgh	IN		22.88	87.78	60639
Arāria	IN		26.15	87.51	79021
Arīsh	EG		31.13	33.80	199243
As Safīrah	SY		36.08	37.37	63708
As Salamīyah	SY		35.01	37.05	94887
As Salţ	JO		32.04	35.73	107874
As Samawah	IQ		31.33	45.29	152890
As Sawānī	LY		32.72	13.07	57069
As Sinbillāwayn	EG		30.88	31.46	124020
As Suwayq	OM		23.85	57.44	107143
As Sālimīyah	KW		29.33	48.08	147649
As Sāḩil	EG		27.06	31.34	54094
As-Suwayda	SY		32.71	36.57	59052
Asaba	NG		6.20	6.73	73374
Asadābād	IR		34.78	48.12	55703
Asahi	JP		35.72	140.65	64690
Asahikawa	JP		43.77	142.36	333530
Asaka	JP		35.80	139.60	141083
Asaka	UZ		40.64	72.24	62200
Asakura	JP		33.41	130.72	50273
Asakusa	JP		35.72	139.80	62092
Asan	KR		36.78	127.00	97749
Asbest	RU		57.01	61.46	74583
Asbury Park	US	New Jersey	40.22	-74.01	15818
Aschaffenburg	DE		49.98	9.15	68551
Ascot	GB		51.41	-0.67	17899
Ascot Vale	AU		-37.78	144.92	15197
Asenovgrad	BG		42.02	24.87	54778
Ash Shafā	SA		21.07	40.32	72190
Ash Sharqāt	IQ		35.52	43.23	160000
Ash Shaţrah	IQ		31.41	46.17	182175
Ash Shuhadā’	EG		30.60	30.90	76071
Ash Shāmīyah	IQ		31.96	44.60	57661
Ash-Shaykh Zāyid	EG		30.02	31.00	95854
Ashaiman	GH		5.70	-0.03	190972
Ashburn	US	Virginia	39.04	-77.49	43511
Ashburn	US	Illinois	41.75	-87.71	42752
Ashburton	NZ		-43.90	171.73	21600
Ashdod	IL		31.79	34.65	226838
Asheboro	US	North Carolina	35.71	-79.81	26103
Asheville	US	North Carolina	35.60	-82.55	95056
Ashfield	AU		-33.89	151.12	23749
Ashford	GB		51.15	0.87	62787
Ashford	GB		51.43	-0.46	27382
Ashgabat	TM		37.95	58.38	1030063
Ashikaga	JP		36.33	139.45	144746
Ashington	GB		55.18	-1.56	27670
Ashiya	JP		34.73	135.30	93922
Ashkelon	IL		31.67	34.57	144073
Ashland	US	California	37.69	-122.11	21925
Ashland	US	Kentucky	38.48	-82.64	21108
Ashland	US	Oregon	42.19	-122.71	20861
Ashland	US	Ohio	40.87	-82.32	20317
Ashland	US	Massachusetts	42.26	-71.46	15802
Ashmont	US	Massachusetts	42.28	-71.07	30000
Ashmūn	EG		30.30	30.98	124483
Ashoknagar	IN		24.58	77.73	81828
Ashoknagar Kalyangarh	IN		22.86	88.64	111475
Ashta	IN		23.02	76.72	53184
Ashtabula	US	Ohio	41.87	-80.79	18371
Ashton in Makerfield	GB		53.48	-2.65	26380
Ashton-under-Lyne	GB		53.49	-2.10	43675
Ashuganj City	BD		24.04	91.01	210356
Ashwaubenon	US	Wisconsin	44.48	-88.07	17176
Asker	NO		59.83	10.44	61906
Asmara	ER		15.34	38.93	563930
Asnières-sur-Seine	FR		48.92	2.28	86742
Aspen Hill	US	Maryland	39.08	-77.07	48759
Aspern	AT		48.22	16.48	50687
Assen	NL		53.00	6.56	68836
Assi Bou Nif	DZ		35.69	-0.50	53700
Assis	BR		-22.66	-50.41	105087
Assiut	EG		27.18	31.18	528669
Astana	KZ		51.18	71.45	1544142
Astanajapura	ID		-6.80	108.63	148047
Asti	IT		44.90	8.21	74348
Aston	GB		52.50	-1.88	32286
Astoria	US	New York	40.77	-73.93	150165
Astrakhan	RU		46.35	48.04	533925
Asunción	PY		-25.29	-57.65	1482200
Aswān	EG		24.09	32.90	379774
At Tall	SY		33.61	36.31	55561
Atakpamé	TG		7.53	1.13	80683
Atambua	ID		-9.11	124.89	82196
Atani	NG		6.01	6.75	230000
Atascadero	US	California	35.49	-120.67	29819
Atascocita	US	Texas	30.00	-95.18	65844
Ataşehir	TR		40.98	29.12	361615
Atbara	SD		17.70	33.99	112021
Athens	GR		37.98	23.73	664046
Athens	US	Georgia	33.96	-83.38	127315
Athens	US	Ohio	39.33	-82.10	25044
Athens	US	Alabama	34.80	-86.97	24966
Atherton	GB		53.52	-2.49	22000
Athi River	KE		-1.46	36.98	81302
Athlone	ZA		-33.97	18.50	237414
Athlone	IE		53.42	-7.94	22869
Atibaia	BR		-23.12	-46.55	144088
Atlanta	US	Georgia	33.75	-84.39	510823
Atlantic City	US	New Jersey	39.36	-74.42	39260
Atlantis	ZA		-33.57	18.48	82736
Atlixco	MX		18.91	-98.44	86690
Atsiaman	GH		5.70	-0.33	202932
Atsugi	JP		35.44	139.37	223960
Attili	IN		16.70	81.60	68196
Attleboro	US	Massachusetts	41.94	-71.29	44284
Attock City	PK		33.77	72.36	141945
Attur	IN		11.59	78.60	61793
Atwater	US	California	37.35	-120.61	29237
Atwater Village	US	California	34.12	-118.26	15455
Atyrau	KZ		47.10	51.88	290700
Aubervilliers	FR		48.92	2.38	70914
Auburn	US	Washington	47.31	-122.23	77006
Auburn	US	Alabama	32.61	-85.48	62059
Auburn	AU		-33.85	151.03	37245
Auburn	US	New York	42.93	-76.57	26985
Auburn	US	Maine	44.10	-70.23	22871
Auburn	US	Massachusetts	42.19	-71.84	16724
Auburn Bay	CA		50.89	-113.96	18090
Auburn Gresham	US	Illinois	41.74	-87.65	45842
Auburn Hills	US	Michigan	42.69	-83.23	22672
Auburndale	US	Florida	28.07	-81.79	15035
Auchi	NG		7.07	6.26	62907
Auckland	NZ		-36.85	174.76	1547200
Augsburg	DE		48.37	10.90	301105
Augusta	US	Georgia	33.47	-81.97	43459
Augusta	US	Maine	44.31	-69.78	18899
Aulnay-sous-Bois	FR		48.94	2.49	80615
Auraiya	IN		26.47	79.51	70508
Aurangabad	IN		19.88	75.34	1175116
Aurangābād	IN		24.75	84.37	102244
Aurora	US	Colorado	39.73	-104.83	359407
Aurora	US	Illinois	41.76	-88.32	200661
Aurora	CA		44.00	-79.47	55445
Aurora	US	Ohio	41.32	-81.35	15838
Austin	US	Texas	30.27	-97.74	974447
Austin	US	Minnesota	43.67	-92.97	24563
Austintown	US	Ohio	41.10	-80.76	29677
Australind	AU		-33.28	115.72	15988
Avadi	IN		13.11	80.11	345996
Avan	AM		40.21	44.58	58800
Avaniyāpuram	IN		9.88	78.11	89635
Avarua	CK		-21.21	-159.78	13373
Avaré	BR		-23.10	-48.93	96098
Avedøre	DK		55.63	12.46	53443
Aveiro	PT		40.65	-8.65	80880
Avellaneda	AR		-34.66	-58.37	367554
Avenel	US	New Jersey	40.58	-74.29	17011
Aventura	US	Florida	25.96	-80.14	37649
Aversa	IT		40.97	14.21	52974
Avignon	FR		43.95	4.81	89769
Avilés	ES		43.55	-5.92	78715
Avocado Heights	US	California	34.04	-117.99	15411
Avon	US	Ohio	41.45	-82.04	22544
Avon	US	Connecticut	41.81	-72.83	18932
Avon	US	Indiana	39.76	-86.40	16451
Avon Center	US	Ohio	41.46	-82.02	15724
Avon Lake	US	Ohio	41.51	-82.03	23453
Avondale	US	Arizona	33.44	-112.35	80684
Avondale	US	Illinois	41.94	-87.71	39721
Avondale	NZ		-36.88	174.70	26450
Avtozavodskyi	UA		49.10	33.43	157382
Awasa	ET		7.06	38.48	422200
Awka	NG		6.21	7.07	167738
Awsīm	EG		30.12	31.14	94174
Ayacucho	PE		-13.16	-74.22	140033
Ayapel	CO		8.31	-75.14	56082
Ayase	JP		35.44	139.43	83913
Aydın	TR		37.85	27.84	163022
Aylesbury	GB		51.82	-0.81	74748
Aylmer	CA		45.40	-75.81	56542
Ayodhya	IN		26.80	82.20	53293
Ayr	GB		55.46	-4.63	46260
Ayvalık	TR		39.32	26.69	70002
Az Zubayr	IQ		30.39	47.70	122676
Az Zulfī	SA		26.30	44.82	125000
Az Zāwīyah	LY		32.76	12.73	200000
Azamgarh	IN		26.07	83.18	116644
Azare	NG		11.67	10.19	105687
Azcapotzalco	MX		19.49	-99.19	414711
Azimpur	BD		23.73	90.39	96641
Azov	RU		47.11	39.41	82133
Azrou	MA		33.43	-5.22	59348
Azua	DO		18.45	-70.73	59139
Azul	AR		-36.78	-59.86	64884
Azumino	JP		36.29	137.89	94222
Azusa	US	California	34.13	-117.91	49690
Az̧ Z̧a‘āyin	QA		25.58	51.48	54339
Az̧ Z̧ulayl	JO		32.12	36.28	50931
Açailândia	BR		-4.95	-47.50	106550
Açu	BR		-5.58	-36.91	56496
Aïn Beïda	DZ		35.80	7.39	116064
Aïn Defla	DZ		36.26	1.97	55259
Aïn Harrouda	MA		33.64	-7.45	68161
Aïn M’Lila	DZ		36.04	6.57	65371
Aïn Oulmene	DZ		35.92	5.30	51207
Aïn Oussera	DZ		35.45	2.91	98107
Aïn Temouchent	DZ		35.30	-1.14	70810
Aïn Touta	DZ		35.38	5.90	55736
Ağrı	TR		39.71	43.04	124483
Aş Şaff	EG		29.56	31.28	61531
Aş Şuwayrah	IQ		32.93	44.78	77200
Aş Şāliḩīyah al Jadīdah	EG		30.63	31.94	59320
Ba Dinh	VN		21.04	105.83	221893
Ba Vì	VN		21.08	105.38	282600
Ba Đồn	VN		17.75	106.42	106413
Bab Ezzouar	DZ		36.73	3.18	275630
Babahoyo	EC		-1.80	-79.52	76279
Babamba	CD		0.18	27.48	81740
Babati	TZ		-4.22	35.75	67445
Babu	CN		24.42	111.52	65603
Babushkin	RU		55.87	37.73	86000
Babīlā	SY		33.47	36.33	50880
Bacabal	BR		-4.23	-44.78	103711
Bacchus Marsh	AU		-37.67	144.44	24717
Bachuan	CN		29.85	106.05	208520
Back Bay	US	Massachusetts	42.35	-71.09	17577
Back Mountain	US	Pennsylvania	41.34	-76.00	26973
Bacolod City	PH		10.67	122.95	454898
Bacoor	PH		14.46	120.94	356974
Bacău	RO		46.57	26.91	136087
Bad Homburg vor der Höhe	DE		50.23	8.62	51859
Bad Salzuflen	DE		52.09	8.74	54899
Bada Barabīl	IN		22.11	85.39	56870
Badagara	IN		11.60	75.58	76493
Badajoz	ES		38.88	-6.97	150530
Badalona	ES		41.45	2.25	217741
Bade	TW		24.93	121.28	209148
Baden-Baden	DE		48.76	8.24	56881
Badger	US	Alaska	64.80	-147.53	19482
Badin	PK		24.66	68.84	117455
Badlapur	IN		19.16	73.27	174226
Badvel	IN		14.75	79.06	70626
Baekrajan	ID		-6.77	110.85	57920
Bafang	CM		5.16	10.18	54505
Bafia	CM		4.75	11.23	74050
Bafoussam	CM		5.48	10.42	373268
Bafra	TR		41.57	35.90	92944
Bagaha	IN		27.10	84.09	112634
Bagaha	IN		24.53	85.06	91383
Bagalkot	IN		16.19	75.70	111933
Bagamoyo	TZ		-6.44	38.90	82426
Bagbera	IN		22.76	86.19	78356
Bageqi	CN		37.14	79.84	57153
Bagerhat	BD		22.66	89.79	266388
Baghdad	IQ		33.34	44.40	7216000
Bagheria	IT		38.08	13.51	53149
Baghlān	AF		36.13	68.71	108449
Bago	MM		17.34	96.48	244376
Bago City	PH		10.53	122.83	192993
Bagong Barrio	PH		14.67	120.99	77490
Bagong Silang	PH		14.78	121.04	261729
Bagong Silangan	PH		14.71	121.11	106886
Baguio	PH		16.42	120.59	272714
Bagé	BR		-31.33	-54.11	98940
Bahadurgarh	IN		28.69	76.94	170767
Baharampur	IN		24.10	88.25	180547
Bahawalnagar	PK		30.00	73.25	241873
Bahawalnagar	PK		30.55	73.39	241873
Bahawalpur	PK		29.40	71.68	903795
Baheri	IN		28.77	79.50	63953
Bahir Dar	ET		11.59	37.39	350000
Bahlā’	OM		22.98	57.30	54338
Bahraigh	IN		27.57	81.59	182218
Bahçelievler	TR		41.00	28.86	576799
Bahía Blanca	AR		-38.72	-62.27	299101
Bahārestān	IR		32.49	51.77	106433
Baia Mare	RO		47.66	23.57	108759
Baicheng	CN		45.62	122.83	316970
Baicheng	CN		36.33	119.78	77235
Baidi	CN		31.06	109.59	56216
Baidoa	SO		3.11	43.65	129839
Baidyabāti	IN		22.78	88.33	115504
Baie-Comeau	CA		49.22	-68.15	21536
Baihecun	CN		22.11	107.24	63629
Baijiantan	CN		45.69	85.14	93697
Baikonur	KZ		45.62	63.32	70000
Baildon	GB		53.85	-1.79	15710
Baileys Crossroads	US	Virginia	38.85	-77.13	23643
Bailundo	AO		-9.57	15.99	70481
Baimajing	CN		19.71	109.22	59585
Bainbridge Island	US	Washington	47.63	-122.52	23840
Baiquan	CN		47.61	126.08	70472
Bairnsdale	AU		-37.82	147.61	17666
Bairro da Penha	BR		-23.37	-46.31	117691
Bairro Militar	GW		11.87	-15.62	65274
Bairro Parque Nossa Senhora do Carmo	BR		-23.41	-46.32	69630
Bais	PH		9.59	123.12	88050
Baise	CN		23.89	106.63	686078
Baisha	CN		29.06	106.12	115761
Baisha	CN		21.72	109.68	89759
Baishan	CN		41.94	126.42	183880
Baishishan	CN		43.58	127.57	56992
Baixi	CN		28.70	104.55	88251
Baiyin	CN		36.55	104.17	294400
Baião	BR		-2.79	-49.67	51641
Bai’anba	CN		30.76	108.44	91947
Bajos de Haina	DO		18.42	-70.03	66784
Bakersfield	US	California	35.37	-119.02	373640
Bakhmut	UA		48.59	38.00	80500
Baki	ID		-7.61	110.78	58909
Baku	AZ		40.38	49.89	2351300
Bakwa	CD		4.13	27.40	100575
Bakıxanov	AZ		40.42	49.97	66686
Balagtas	PH		14.82	120.87	59826
Balai Pungut	ID		1.06	101.29	56452
Balakovo	RU		52.03	47.80	199572
Balanbale	SO		5.77	45.76	68000
Balanga	PH		14.68	120.54	72954
Balashikha	RU		55.79	37.95	150103
Balashov	RU		51.55	43.17	98107
Balasore	IN		21.49	86.93	144373
Balayan	PH		13.94	120.73	50115
Balbala	DJ		11.56	43.11	554350
Balbriggan	IE		53.61	-6.18	21722
Balch Springs	US	Texas	32.73	-96.62	25210
Balcón de la Lisa	CU		23.05	-82.45	147415
Baldivis	AU		-32.33	115.83	37697
Baldwin	US	New York	40.66	-73.61	24033
Baldwin	US	Pennsylvania	40.34	-79.98	19819
Baldwin Park	US	California	34.09	-117.96	77071
Balikpapan	ID		-1.27	116.83	695287
Baliuag	PH		14.95	120.90	135679
Baljurashi	SA		19.86	41.56	51787
Balkanabat	TM		39.51	54.37	87822
Balkh	AF		36.76	66.90	114883
Ballajura	AU		-31.84	115.90	18459
Ballarat	AU		-37.57	143.85	111973
Ballari	IN		15.14	76.92	410445
Ballarpur	IN		19.85	79.35	92146
Ballenger Creek	US	Maryland	39.37	-77.44	18274
Ballincollig	IE		51.88	-8.58	18621
Ballwin	US	Missouri	38.60	-90.55	30577
Ballymena	GB		54.86	-6.28	28932
Balneário Camboriú	BR		-26.99	-48.63	139155
Balombo	AO		-12.35	14.77	108965
Balotra	IN		25.83	72.24	74496
Balqash	KZ		46.85	74.98	81364
Balrāmpur	IN		27.43	82.19	77396
Balsas	BR		-7.53	-46.04	101767
Baltimore	US	Maryland	39.29	-76.61	585708
Balvanera	AR		-34.61	-58.40	152198
Balwyn North	AU		-37.79	145.09	21302
Balāngīr	IN		20.70	83.49	98238
Balıkesir	TR		39.65	27.89	238151
Balţīm	EG		31.56	31.09	51280
Bam	IR		29.11	58.36	99268
Bama	NG		11.52	13.69	118121
Bamako	ML		12.61	-7.98	4227569
Bamban	PH		15.27	120.57	78260
Bambang	PH		16.39	121.11	60146
Bambari	CF		5.77	20.68	83029
Bamberg	DE		49.90	10.90	70047
Bamenda	CM		5.96	10.15	420445
Ban I Chang	TH		13.71	99.90	119858
Ban Khlong Prawet	TH		13.72	100.68	160671
Ban Khoan	LA		20.35	100.09	65348
Ban Ko Sire	TH		7.89	98.43	71284
Ban Lak Song	TH		13.69	100.40	52144
Ban Lam Luk Ka	TH		13.98	100.78	60700
Ban Mai	TH		7.20	100.55	86899
Ban Pong	TH		13.82	99.88	57559
Ban Samae Dam	TH		13.59	100.39	125133
Ban Talat Yai	TH		7.88	98.40	52192
Ban Tha Kham	TH		13.64	100.44	61011
Banan	CN		29.38	106.54	508703
Banbridge	GB		54.35	-6.28	16173
Banbury	GB		52.06	-1.34	48651
Banbury-Don Mills	CA		43.74	-79.35	27695
Banco Filipino Homes	PH		14.43	121.02	92752
Banda Aceh	ID		5.54	95.33	267962
Bandar Abbas	IR		27.19	56.28	352173
Bandar Bukit Raja	MY		3.09	101.43	146534
Bandar Kinrara	MY		3.05	101.64	93822
Bandar Labuan	MY		5.28	115.25	54752
Bandar Lampung	ID		-5.43	105.26	1166066
Bandar Mahkota Cheras	MY		3.05	101.80	100000
Bandar Saujana Utama	MY		3.21	101.48	72000
Bandar Seri Alam	MY		1.50	103.88	220000
Bandar Seri Begawan	BN		4.89	114.94	64409
Bandar Sunway	MY		3.07	101.61	200000
Bandar Tasik Puteri	MY		3.29	101.47	150000
Bandar Utama	MY		3.15	101.61	200000
Bandar-e Anzalī	IR		37.47	49.46	118564
Bandar-e Emam Khomeyni	IR		30.44	49.10	78353
Bandar-e Genāveh	IR		29.58	50.52	52750
Bandar-e Kangān	IR		27.83	52.06	60187
Bandar-e Māhshahr	IR		30.56	49.19	162797
Bandar-e Torkaman	IR		36.90	54.07	53970
Bandundu Province	CD		-3.32	17.38	202904
Bandung	ID		-6.92	107.61	2528163
Bandırma	TR		40.35	27.98	107631
Bandō	JP		36.07	139.87	57128
Banepā	NP		27.63	85.52	67629
Banes	CU		20.96	-75.72	53104
Banfield	AR		-34.75	-58.39	61072
Banfora	BF		10.64	-4.75	117452
Bang Bon	TH		13.66	100.40	105161
Bang Kapi	TH		13.77	100.65	147800
Bang Khae	TH		13.69	100.41	193002
Bang Khae Nuea	TH		13.71	100.39	59821
Bang Khun Thian	TH		13.66	100.43	165491
Bang Kruai	TH		13.80	100.47	78305
Bang Na	TH		13.67	100.64	95912
Bang Phlat	TH		13.79	100.50	92325
Bang Rak	TH		13.73	100.52	99273
Bang Sue	TH		13.81	100.53	125440
Bang Sue subdistrict	TH		13.81	100.53	79405
Banga	PH		6.42	124.78	91536
Bangaon	IN		23.05	88.83	111693
Bangaon	IN		25.87	86.51	60000
Bangassou	CF		4.74	22.82	54059
Bangil	ID		-7.60	112.82	85504
Bangkalan	ID		-7.05	112.74	86250
Bangkok	TH		13.75	100.50	5104476
Bangkok Noi	TH		13.76	100.48	117793
Bangkok Yai	TH		13.72	100.48	72321
Bangor	GB		54.66	-5.67	61011
Bangor	US	Maine	44.80	-68.77	32391
Bangor	GB		53.23	-4.13	18322
Bangui	CF		4.36	18.55	812407
Banhā	EG		30.46	31.18	182254
Bani Yas City	AE		24.31	54.63	80498
Banja Luka	BA		44.78	17.21	221106
Banjar	ID		-7.20	107.43	209791
Banjar	ID		-8.19	114.97	89040
Banjaran	ID		-7.05	107.59	164952
Banjarbaru	ID		-3.44	114.84	293332
Banjarmasin	ID		-3.32	114.59	657663
Banjul	GM		13.45	-16.58	37274
Bankra	IN		22.60	88.28	56273
Bankstown	AU		-33.92	151.03	34933
Banning	US	California	33.93	-116.88	30945
Bannu	PK		32.99	70.60	1357890
Banora Point	AU		-28.21	153.54	15868
Banqiao	TW		25.01	121.47	551221
Banská Bystrica	SK		48.74	19.15	74590
Banstead	GB		51.32	-0.21	46280
Bantayan	PH		11.17	123.72	87394
Bantul	ID		-7.89	110.33	64360
Banyuwangi	ID		-8.23	114.36	117558
Baní	DO		18.28	-70.33	66709
Banī Mazār	EG		28.49	30.81	115759
Banī Suwayf	EG		29.07	31.10	273151
Bao'an	CN		22.55	113.88	4476554
Bao'an Centre	CN		22.58	113.92	120170
Baoding	CN		38.87	115.46	2739887
Baoji	CN		34.37	107.24	1437802
Baoqing	CN		46.32	132.19	62991
Baoshan	CN		31.41	121.49	2265900
Baoshan	CN		25.12	99.16	935618
Baoshan	CN		46.57	131.39	123791
Baotou	CN		40.65	109.84	2150000
Baoying	CN		33.23	119.31	80292
Baqubah	IQ		33.75	44.61	152550
Barabai	ID		-2.58	115.38	55956
Barakaldo	ES		43.30	-2.99	100435
Baraki	DZ		36.67	3.10	105402
Baranagar	IN		22.64	88.38	260072
Baranoa	CO		10.79	-74.92	68383
Baranovichi	BY		53.13	26.01	170039
Barauni	IN		25.47	85.98	71660
Baraut	IN		29.10	77.26	93544
Barbacena	BR		-21.23	-43.77	125317
Barbalha	BR		-7.31	-39.30	75033
Barberton	ZA		-25.79	31.05	67927
Barberton	US	Ohio	41.01	-81.61	26234
Barbil	IN		22.10	85.38	66540
Barbosa	CO		6.44	-75.33	53943
Barcarena	BR		-1.51	-48.63	126650
Barcelona	ES		41.39	2.16	1686208
Barcelona	VE		10.14	-64.69	815141
Barddhamān	IN		23.26	87.86	301725
Bareilly	IN		28.37	79.43	745435
Bargarh	IN		21.33	83.62	80625
Bargny	SN		14.70	-17.23	69242
Bargny Guèdj	SN		14.69	-17.23	51188
Bargny Ngoude	SN		14.69	-17.24	51188
Bari	IT		41.12	16.87	316491
Bariadi	TZ		-2.80	33.98	260927
Barika	DZ		35.39	5.37	98141
Barinas	VE		8.62	-70.23	397279
Barinitas	VE		8.76	-70.41	51556
Baripāda	IN		21.93	86.73	116849
Bariq	SA		18.93	41.93	75351
Barishal	BD		22.70	90.37	202242
Barkam	CN		31.90	102.22	58390
Barking	GB		51.53	0.08	218534
Barkā’	OM		23.68	57.89	81647
Barletta	IT		41.31	16.28	93279
Barnaul	RU		53.36	83.73	632372
Barnes	GB		51.47	-0.25	21218
Barnet	GB		51.65	-0.20	30000
Barnsley	GB		53.55	-1.48	71447
Barnstable	US	Massachusetts	41.70	-70.30	47821
Barnstaple	GB		51.08	-4.06	31616
Barnāla	IN		30.37	75.55	116449
Barquisimeto	VE		10.06	-69.36	1240714
Barra	BR		-11.09	-43.14	51092
Barra do Corda	BR		-5.51	-45.24	86662
Barra do Dande	AO		-8.47	13.37	75000
Barra do Garças	BR		-15.89	-52.26	72694
Barra do Piraí	BR		-22.47	-43.83	98501
Barra Mansa	BR		-22.54	-44.17	164052
Barracas	AR		-34.65	-58.38	77474
Barrancabermeja	CO		7.07	-73.85	191403
Barranqueras	AR		-27.48	-58.94	50823
Barranquilla	CO		10.97	-74.78	1206319
Barreiras	BR		-12.15	-44.99	159734
Barreirinhas	BR		-2.76	-42.83	65589
Barreiro	PT		38.66	-9.07	51280
Barretos	BR		-20.56	-48.57	122485
Barrhead	GB		55.80	-4.39	17890
Barri de Sant Andreu	ES		41.44	2.19	56818
Barrie	CA		44.40	-79.67	147829
Barriera di Lanzo	IT		45.11	7.65	50000
Barriera di Milano	IT		45.09	7.69	50354
Barrington	US	Rhode Island	41.74	-71.31	16669
Barrow in Furness	GB		54.11	-3.23	55489
Barry	GB		51.40	-3.28	54673
Barshi	IN		18.23	75.69	118722
Barstow	US	California	34.90	-117.02	23692
Barstow Heights	US	California	34.87	-117.06	24202
Bartlesville	US	Oklahoma	36.75	-95.98	36595
Bartlett	US	Tennessee	35.20	-89.87	58579
Bartlett	US	Illinois	42.00	-88.19	41545
Bartley Green	GB		52.44	-2.00	22670
Bartolomé Masó	CU		20.17	-76.94	53024
Bartow	US	Florida	27.90	-81.84	18972
Bartın	TR		41.64	32.34	81692
Barueri	BR		-23.51	-46.88	316473
Baruipur	IN		22.37	88.43	53128
Baruta	VE		10.43	-66.88	244216
Barwāni	IN		22.03	74.90	55504
Barysaw	BY		54.23	28.50	133700
Basavakalyan	IN		17.87	76.95	69717
Basel	CH		47.56	7.57	177595
Basford	GB		52.97	-1.18	16000
Bashan	CN		27.77	116.05	103748
Basildon	GB		51.57	0.46	144859
Basingstoke	GB		51.26	-1.09	107642
Basirhat City	IN		22.66	88.85	143007
Basirpur	PK		30.58	73.84	65541
Basking Ridge	US	New Jersey	40.71	-74.55	21424
Basmat	IN		19.33	77.16	68846
Basoda	IN		23.85	77.94	78289
Basoko	CD		1.24	23.62	76371
Basrah	IQ		30.51	47.78	1326564
Bassar	TG		9.25	0.78	61845
Basse-Terre	GP		16.00	-61.73	11472
Basseterre	KN		17.30	-62.72	12920
Bastī	IN		26.79	82.72	115115
Basuo	CN		19.10	108.67	444458
Basyūn	EG		30.94	30.81	75084
Bat Khela	PK		34.62	71.97	73525
Bat Yam	IL		32.02	34.75	129012
Bata	GQ		1.86	9.77	173046
Batac City	PH		18.06	120.56	56781
Batam	ID		1.15	104.02	1296960
Batang	ID		-6.48	110.71	139492
Batangas	PH		13.76	121.06	237370
Batatais	BR		-20.89	-47.59	58402
Batavia	US	Illinois	41.85	-88.31	26495
Batavia	US	New York	43.00	-78.19	15010
Bataysk	RU		47.14	39.76	109962
Batemans Bay	AU		-35.71	150.18	17519
Bath	GB		51.38	-2.36	101557
Bath Beach	US	New York	40.60	-74.00	33080
Bathgate	GB		55.90	-3.64	23600
Bathinda	IN		30.21	74.94	285788
Bathurst	AU		-33.42	149.58	36230
Bathurst Manor	CA		43.76	-79.46	15873
Batikent	TR		39.97	32.73	300000
Batley	GB		53.70	-1.63	39013
Batman	TR		37.89	41.13	452157
Batna	DZ		35.56	6.17	289504
Baton Rouge	US	Louisiana	30.44	-91.19	227470
Battagram	PK		34.68	73.02	700000
Battambang	KH		13.10	103.20	119251
Battaramulla South	LK		6.90	79.92	75633
Battersea	GB		51.47	-0.16	75651
Batticaloa	LK		7.71	81.69	86742
Battir	PS		31.70	35.12	56746
Battle Creek	US	Michigan	42.32	-85.18	51589
Battle Ground	US	Washington	45.78	-122.53	19407
Batu	ID		-7.87	112.53	225408
Batu Caves	MY		3.24	101.68	254083
Batu Pahat	MY		1.85	102.93	156236
Batumi	GE		41.64	41.63	186949
Baturaja	ID		-4.13	104.17	134759
Batāla	IN		31.81	75.20	158621
Bau	MY		1.42	110.15	52643
Bauang	PH		16.53	120.33	77670
Baubau	ID		-5.46	122.60	161280
Bauchi	NG		10.31	9.84	693700
Baudhuinville	CD		-7.08	29.74	81181
Baulkham Hills	AU		-33.76	150.99	36792
Bauru	BR		-22.31	-49.06	379297
Bawku	GH		11.06	-0.24	76459
Bawshar	OM		23.58	58.40	383257
Bawāna	IN		28.80	77.03	73680
Bay City	US	Michigan	43.59	-83.89	33917
Bay City	US	Texas	28.98	-95.97	17598
Bay Point	US	California	38.03	-121.96	21534
Bay Shore	US	New York	40.73	-73.25	26337
Bay Street Corridor	CA		43.66	-79.39	25797
Bay Village	US	Ohio	41.48	-81.92	15402
Bayambang	PH		15.81	120.46	129506
Bayamo	CU		20.37	-76.64	192632
Bayamón	PR		18.40	-66.16	203499
Bayan	CN		46.08	127.39	55186
Bayan Hot	CN		38.84	105.67	94445
Bayan Lepas	MY		5.30	100.26	130455
Bayan Nur	CN		40.74	107.39	1760000
Bayawan	PH		9.36	122.80	126744
Baychester	US	New York	40.87	-73.84	16274
Bayeux	BR		-7.12	-34.93	82742
Bayiji	CN		34.27	117.68	65830
Bayjī	IQ		34.93	43.49	173677
Bayonet Point	US	Florida	28.33	-82.68	23467
Bayonne	US	New Jersey	40.67	-74.11	66311
Bayou Cane	US	Louisiana	29.62	-90.75	19355
Bayramaly	TM		37.62	62.17	70376
Bayreuth	DE		49.95	11.58	72940
Bayshore Gardens	US	Florida	27.43	-82.59	16323
Bayside	US	New York	40.77	-73.78	66455
Bayside	US	California	40.84	-124.06	17132
Bayswater	GB		51.51	-0.18	17500
Bayt Lāhyā	PS		31.55	34.50	56919
Baytown	US	Texas	29.74	-94.98	76335
Bayugan	PH		8.76	125.77	110313
Bayview Village	CA		43.78	-79.38	21396
Bayview-Hunters Point	US	California	37.73	-122.38	34835
Bayville	US	New Jersey	39.91	-74.15	20512
Bazhong	CN		31.87	106.74	2712894
Baía Farta	AO		-12.60	13.20	107841
Bañga	PH		6.42	124.78	58855
Bağcılar	TR		41.04	28.86	740069
Başakşehir	TR		41.11	28.79	193750
Baḥarkah	IQ		36.32	44.04	130518
Beaconsfield	CA		45.43	-73.87	19194
Bear	US	Delaware	39.63	-75.66	19371
Bearsden	GB		55.92	-4.33	28470
Beau Bassin-Rose Hill	MU		-20.23	57.47	111355
Beaumont	US	Texas	30.09	-94.10	115282
Beaumont	US	California	33.93	-116.98	43811
Beauport	CA		46.86	-71.19	81425
Beauvais	FR		49.43	2.08	53393
Beaver Dam	US	Wisconsin	43.46	-88.84	16564
Beavercreek	US	Ohio	39.71	-84.06	46277
Beaverton	US	Oregon	45.49	-122.80	96577
Bebedouro	BR		-20.95	-48.48	76373
Beberibe	BR		-4.18	-38.13	53114
Bebington	GB		53.35	-3.02	57600
Beckenham	GB		51.41	-0.03	60739
Beckley	US	West Virginia	37.78	-81.19	17056
Becontree	GB		51.55	0.13	100000
Bedford	GB		52.13	-0.47	106940
Bedford	US	Texas	32.84	-97.14	49337
Bedford	CA		44.73	-63.67	21474
Bedford	US	New Hampshire	42.95	-71.52	21188
Bedford Park-Nortown	CA		43.73	-79.42	23236
Bedlington	GB		55.13	-1.59	18470
Bedok New Town	SG		1.33	103.94	276990
Bedworth	GB		52.48	-1.47	31090
Beed	IN		18.99	75.76	146709
Beersheba	IL		31.25	34.79	186600
Begampur	IN		28.73	77.07	53682
Begusarai	IN		25.42	86.13	252008
Behbahān	IR		30.60	50.24	122604
Behshahr	IR		36.69	53.55	94702
Beibei	CN		29.83	106.44	247702
Beichengqu	CN		40.44	113.15	72444
Beidao	CN		34.57	105.89	74767
Beihai	CN		21.48	109.12	525329
Beijing	CN		39.91	116.40	18960744
Beiliu	CN		22.71	110.35	199769
Beimeng	CN		36.60	119.50	66277
Beining	CN		41.60	121.79	152033
Beipiao	CN		41.79	120.78	190315
Beira	MZ		-19.84	34.84	687764
Beirut	LB		33.89	35.50	1916100
Beisu	CN		38.15	114.81	52752
Beitbridge	ZW		-22.22	30.00	58574
Bei’an	CN		48.27	126.60	436444
Bejaâd	MA		32.77	-6.39	51206
Bekasi	ID		-6.23	106.99	2648272
Bekobod	UZ		40.22	69.27	96900
Bel Air North	US	Maryland	39.55	-76.37	30568
Bel Air South	US	Maryland	39.51	-76.32	47709
Bela	IN		25.92	82.00	73992
Bela Bela	ZA		-24.88	28.28	90210
Bela Vista	BR		-23.56	-46.65	60024
Belagavi	IN		15.85	74.50	490045
Belawan	ID		3.78	98.68	102707
Belebey	RU		54.11	54.12	62582
Beled Hawo	SO		3.93	41.88	73000
Beledweyne	SO		4.74	45.20	55410
Belek	TR		36.86	31.07	73260
Belem	BR		-23.54	-46.59	55785
Belen	PE		-3.76	-73.25	57824
Belfast	GB		54.60	-5.93	348005
Belford Roxo	BR		-22.76	-43.40	466096
Belfort	FR		47.64	6.85	54562
Belgorod	RU		50.60	36.58	345289
Belgrade	RS		44.80	20.47	1273651
Belgrano	AR		-34.56	-58.46	138942
Beliatta	LK		6.05	80.73	58675
Belize City	BZ		17.50	-88.20	65222
Bell	US	California	33.98	-118.19	36205
Bell Gardens	US	California	33.97	-118.15	43106
Bella Vista	DO		18.46	-69.95	175683
Bella Vista	AR		-34.57	-58.69	79737
Bella Vista	US	Arkansas	36.48	-94.27	27999
Bellaire	US	Texas	29.71	-95.46	18518
Bellampalli	IN		19.06	79.49	66660
Belle Glade	US	Florida	26.68	-80.67	18251
Belle Vale	GB		53.39	-2.86	15613
Belleville	CA		44.17	-77.38	50716
Belleville	US	Illinois	38.52	-89.98	42034
Belleville	US	New Jersey	40.79	-74.15	36878
Bellevue	US	Washington	47.61	-122.20	139820
Bellevue	US	Nebraska	41.14	-95.89	55510
Bellevue	US	Wisconsin	44.44	-87.92	15317
Bellflower	US	California	33.88	-118.12	78441
Bellingham	US	Washington	48.76	-122.49	85146
Bellmore	US	New York	40.67	-73.53	16218
Bello	CO		6.34	-75.56	392939
Bellshill	GB		55.82	-4.02	19700
Bellview	US	Florida	30.46	-87.31	23355
Bellwood	US	Illinois	41.88	-87.88	19308
Belmont	US	California	37.52	-122.28	27218
Belmont	US	Massachusetts	42.40	-71.18	24729
Belmont Cragin	US	Illinois	41.93	-87.77	79159
Belmopan	BZ		17.25	-88.76	13381
Belo Horizonte	BR		-19.92	-43.94	2721564
Belo Jardim	BR		-8.34	-36.42	83647
Beloeil	CA		45.57	-73.21	18927
Belogorsk	RU		50.91	128.51	67911
Beloit	US	Wisconsin	42.51	-89.03	36891
Belorechensk	RU		44.77	39.87	54526
Beloretsk	RU		53.96	58.40	70468
Belovo	RU		54.42	86.30	75764
Belper	GB		53.02	-1.48	23417
Beltline	CA		51.04	-114.07	25880
Belton	US	Missouri	38.81	-94.53	23168
Belton	US	Texas	31.06	-97.46	20547
Beltsville	US	Maryland	39.03	-76.91	16772
Belvedere Park	US	Georgia	33.75	-84.27	15152
Belvidere	US	Illinois	42.26	-88.84	25132
Belém	BR		-1.46	-48.50	1499641
Bemowo	PL		52.25	20.91	123932
Ben Arous	TN		36.75	10.22	88322
Ben Gardane	TN		33.14	11.22	87404
Ben Guerir	MA		32.24	-7.95	96777
Ben Jerrar	MA		30.26	-9.50	53026
Benalmádena	ES		36.60	-4.57	58854
Benbrook	US	Texas	32.67	-97.46	22629
Bend	US	Oregon	44.06	-121.32	87014
Bendale	CA		43.77	-79.25	29960
Bende	NG		5.56	7.63	79618
Bender	MD		46.83	29.48	110175
Bendigo	AU		-36.76	144.28	103034
Benevento	IT		41.13	14.78	58418
Benevides	BR		-1.36	-48.24	63567
Benfica	AO		-8.94	13.16	191828
Bengaluru	IN		12.97	77.59	8495492
Bengbu	CN		32.94	117.36	972784
Benghazi	LY		32.11	20.07	757490
Bengkulu	ID		-3.80	102.27	397321
Benguela	AO		-12.58	13.40	555124
Beni	CD		0.49	29.47	140731
Beni Enzar	MA		35.26	-2.93	61786
Beni Mellal	MA		32.34	-6.35	210397
Beni Mered	DZ		36.52	2.86	92749
Benicia	US	California	38.05	-122.16	28167
Benidorm	ES		38.54	-0.13	70450
Benin City	NG		6.34	5.63	1782000
Benipur	IN		26.06	86.15	75317
Benito Juarez	MX		19.40	-99.16	355017
Benito Juárez	MX		19.37	-99.16	385439
Benoni	ZA		-26.19	28.32	605344
Bensalem	US	Pennsylvania	40.10	-74.95	60427
Bensenville	US	Illinois	41.96	-87.94	18440
Benslimane	MA		33.62	-7.12	62352
Bensonhurst	US	New York	40.60	-73.99	60000
Bentleigh	AU		-37.92	145.04	17921
Bentleigh East	AU		-37.92	145.05	30159
Bentley	GB		53.53	-1.15	34821
Bento Gonçalves	BR		-29.17	-51.52	123151
Benton	US	Arkansas	34.56	-92.59	34177
Bentonville	US	Arkansas	36.37	-94.21	44499
Benxi	CN		41.29	123.77	987717
Beppu	JP		33.28	131.50	122643
Berat	AL		40.71	19.95	62232
Berazategui	AR		-34.77	-58.21	180523
Berbera	SO		10.44	45.01	242344
Berbérati	CF		4.26	15.79	103713
Bercham	MY		4.64	101.14	150000
Berdsk	RU		54.75	83.10	90250
Berdyansk	UA		46.76	36.79	106311
Berdychiv	UA		49.89	28.58	73046
Berea	US	Ohio	41.37	-81.85	18874
Berekum	GH		7.45	-2.58	70536
Berestovskyi	UA		48.04	37.88	80671
Berezniki	RU		59.41	56.82	167748
Bergama	TR		39.12	27.18	57200
Bergamo	IT		45.70	9.67	121200
Bergedorf	DE		53.48	10.23	119665
Bergen	NO		60.39	5.32	294029
Bergen op Zoom	NL		51.49	4.29	66256
Bergenfield	US	New Jersey	40.93	-74.00	27621
Bergheim	DE		50.96	6.64	63558
Bergisch Gladbach	DE		50.99	7.13	106184
Bergkamen	DE		51.62	7.64	52329
Berisso	AR		-34.87	-57.88	88470
Berkane	MA		34.92	-2.32	119284
Berkeley	US	California	37.87	-122.27	120972
Berkhamsted	GB		51.76	-0.57	21997
Berkley	US	Michigan	42.50	-83.18	15268
Berlin	DE		52.52	13.41	3426354
Berlin Köpenick	DE		52.44	13.58	59561
Bern	CH		46.95	7.45	121631
Berrechid	MA		33.27	-7.59	149201
Berrouaghia	DZ		36.14	2.91	55775
Bertioga	BR		-23.85	-46.14	64723
Bertoua	CM		4.58	13.68	137993
Beruniy	UZ		41.69	60.75	66090
Berwick	AU		-38.03	145.35	50298
Berwyn	US	Illinois	41.85	-87.79	56368
Berëzovskiy	RU		55.67	86.27	55000
Besançon	FR		47.25	6.02	128426
Besbes	DZ		36.70	7.85	66287
Beshariq	UZ		40.44	70.61	96900
Bessemer	US	Alabama	33.40	-86.95	26730
Besuki	ID		-7.73	113.70	55465
Bet Shemesh	IL		31.73	34.99	124957
Bethal	ZA		-26.46	29.47	72821
Bethany	US	Oregon	45.56	-122.87	20646
Bethany	US	Oklahoma	35.52	-97.63	19589
Bethel Park	US	Pennsylvania	40.33	-80.04	32118
Bethesda	US	Maryland	38.98	-77.10	60858
Bethlehem	ZA		-28.23	28.31	91075
Bethlehem	US	Pennsylvania	40.63	-75.37	74892
Bethnal Green	GB		51.53	-0.06	17590
Bethpage	US	New York	40.74	-73.48	16429
Betim	BR		-19.97	-44.20	384000
Bettendorf	US	Iowa	41.52	-90.52	35505
Bettiah	IN		26.80	84.50	132209
Betūl	IN		21.90	77.90	103330
Beverley	GB		53.85	-0.42	30587
Beverly	US	Massachusetts	42.56	-70.88	41186
Beverly Cove	US	Massachusetts	42.55	-70.85	40365
Beverly Hills	US	California	34.07	-118.40	34869
Bexhill-on-Sea	GB		50.85	0.47	43754
Bexley	GB		51.44	0.15	228000
Bexley	AU		-33.95	151.12	19664
Beylikdüzü	TR		40.98	28.64	415290
Beypore	IN		11.17	75.81	70751
Bezerros	BR		-8.23	-35.80	64809
Beāwar	IN		26.10	74.32	151152
Bełchatów	PL		51.37	19.36	62896
Bhabhua	IN		25.04	83.61	50179
Bhadohi	IN		25.40	82.57	78568
Bhadrak	IN		21.05	86.52	121338
Bhadravati	IN		20.10	79.11	60565
Bhadreswar	IN		22.82	88.34	121662
Bhadrāchalam	IN		17.67	80.89	50087
Bhadrāvati	IN		13.85	75.71	163903
Bhairab Bāzār	BD		24.05	90.98	105457
Bhakkar	PK		31.63	71.06	131658
Bhalwal	PK		32.27	72.90	74744
Bhamo	MM		24.25	97.23	54721
Bhandāra	IN		21.17	79.65	91845
Bharatpur	NP		27.68	84.44	369377
Bharatpur	IN		27.22	77.49	252838
Bharūch	IN		21.69	72.98	169007
Bhatara	BD		23.80	90.45	324300
Bhavnagar	IN		21.76	72.15	605882
Bhawana	PK		31.57	72.65	373841
Bhawānipatna	IN		19.91	83.17	69045
Bhayandar	IN		19.30	72.85	809378
Bhetia	IN		22.79	86.14	174355
Bhilai	IN		21.21	81.43	627734
Bhilai Charoda	IN		21.22	81.46	98008
Bhilwara	IN		25.35	74.64	359483
Bhimavaram	IN		16.54	81.52	146961
Bhimdatta	NP		28.96	80.18	88381
Bhind	IN		26.57	78.79	197585
Bhisho	ZA		-32.85	27.44	137287
Bhiwadi	IN		28.21	76.86	104921
Bhiwandi	IN		19.30	73.06	874032
Bhiwāni	IN		28.79	76.14	196057
Bhola	BD		22.69	90.64	99079
Bhongīr	IN		17.52	78.89	53339
Bhopal	IN		23.25	77.40	1798218
Bhubaneswar	IN		20.27	85.83	885363
Bhuj	IN		23.25	69.67	148834
Bhusawal	IN		21.04	75.79	187421
Bhāgalpur	IN		25.24	86.97	400146
Bhālswa Jahangirpur	IN		28.74	77.17	197148
Bhātpāra	IN		22.87	88.40	483129
Bhātāpāra	IN		21.73	81.95	57537
Bhīmunipatnam	IN		17.89	83.45	55082
Bianzhuang	CN		34.85	118.04	65381
Biała Podlaska	PL		52.03	23.12	57541
Białołeka	PL		52.32	20.97	129106
Białystok	PL		53.13	23.16	295683
Bibir Hat	BD		22.68	91.79	89030
Bibirevo	RU		55.88	37.60	159000
Bibā	EG		28.92	30.99	94677
Bicester	GB		51.90	-1.15	33846
Bida	NG		9.08	6.01	400000
Bidar	IN		17.91	77.52	216020
Biddeford	US	Maine	43.49	-70.45	21282
Biddulph	GB		53.12	-2.18	17669
Bideford	GB		51.02	-4.21	28672
Biel/Bienne	CH		47.14	7.25	55120
Bielany	PL		52.29	20.94	131910
Bielefeld	DE		52.03	8.53	331906
Bielsko-Biala	PL		49.82	19.05	176515
Big Spring	US	Texas	32.25	-101.48	28862
Biga	TR		40.23	27.24	61066
Biggleswade	GB		52.09	-0.26	16551
Biguaçu	BR		-27.49	-48.66	76773
Bihać	BA		44.82	15.87	75641
Bihār Sharīf	IN		25.20	85.52	297268
Bihāt	IN		25.43	86.02	67952
Bijie	CN		27.30	105.29	1137383
Bijnor	IN		29.37	78.14	84593
Bikaner	IN		28.02	73.31	644406
Bila Tserkva	UA		49.80	30.12	207273
Bilbao	ES		43.26	-2.93	347342
Bilbeis	EG		30.42	31.56	185237
Bilecik	TR		40.14	29.98	74457
Bilimora	IN		20.77	72.96	510879
Billerica	US	Massachusetts	42.56	-71.27	39904
Billericay	GB		51.63	0.42	36338
Billingham	GB		54.59	-1.29	35708
Billings	US	Montana	45.78	-108.50	117116
Billstedt	DE		53.55	10.13	71077
Biloxi	US	Mississippi	30.40	-88.89	45637
Bilqās	EG		31.21	31.36	137080
Bilāspur	IN		22.08	82.16	365579
Bima	ID		-8.46	118.73	165113
Bimbo	CF		4.26	18.42	348802
Bin Xian	CN		45.74	127.46	62017
Binangonan	PH		14.46	121.19	219204
Bindura	ZW		-17.30	31.33	50400
Binga	CD		2.37	20.50	96790
Bingerville	CI		5.36	-3.89	82983
Binghamton	US	New York	42.10	-75.92	46032
Bingley	GB		53.85	-1.84	18040
Bingöl	TR		38.88	40.49	128935
Binjai	ID		3.60	98.49	279302
Binonga	PH		10.77	122.98	83980
Bintulu	MY		3.17	113.03	151617
Binzhou	CN		37.37	118.02	682717
Bir el Ater	DZ		34.74	8.06	70749
Bir el Djir	DZ		35.72	-0.55	68032
Biratnagar	NP		26.46	87.27	244750
Birchcliffe-Cliffside	CA		43.69	-79.27	22291
Birendranagar	NP		28.60	81.62	154886
Birgaon	IN		21.31	81.63	96294
Birgañj	NP		27.02	84.88	268273
Birigui	BR		-21.29	-50.34	102277
Birkat as Sab‘	EG		30.63	31.08	50924
Birkenhead	GB		53.39	-3.01	325264
Birkhadem	DZ		36.71	3.05	71722
Birmingham	GB		52.48	-1.90	1157603
Birmingham	US	Alabama	33.52	-86.80	196357
Birmingham	US	Michigan	42.55	-83.21	20857
Birni N Konni	NE		13.80	5.25	85494
Birnin Kebbi	NG		12.45	4.20	108164
Birobidzhan	RU		48.79	132.92	73623
Biruaca	VE		7.84	-67.52	76553
Biryulëvo	RU		55.59	37.68	144000
Biryulëvo Zapadnoye	RU		55.59	37.65	89000
Bisceglie	IT		41.24	16.50	55385
Bishan	CN		29.59	106.22	204702
Bishan New Town	SG		1.35	103.85	87320
Bishkek	KG		42.87	74.59	900000
Bishnupur	IN		23.07	87.32	64041
Bishoftu	ET		8.75	38.98	207400
Bishop Auckland	GB		54.66	-1.68	26050
Bishopbriggs	GB		55.91	-4.22	23680
Bishops Stortford	GB		51.87	0.16	40915
Bishopstoke	GB		50.97	-1.33	17667
Biskra	DZ		34.85	5.73	204661
Bislig	PH		8.22	126.32	99872
Bismarck	US	North Dakota	46.81	-100.78	75092
Bismil	TR		37.85	40.66	74493
Bissau	GW		11.86	-15.60	439704
Bistriţa	RO		47.13	24.50	78877
Biswān	IN		27.50	81.00	52516
Bitlis	TR		38.40	42.11	53023
Bitola	MK		41.03	21.34	69287
Bitonto	IT		41.11	16.69	51661
Bitung	ID		1.44	125.13	225134
Biu	NG		10.61	12.19	95005
Bixby	US	Oklahoma	35.94	-95.88	24657
Biyalā	EG		31.17	31.22	89068
Biysk	RU		52.53	85.20	215430
Bizerte	TN		37.27	9.87	138430
Biên Hòa	VN		10.94	106.82	1272235
Biñan	PH		14.34	121.08	300000
Black Creek	CA		43.76	-79.52	21737
Blackburn	GB		53.75	-2.48	146521
Blackheath	GB		51.46	0.01	25116
Blackpool	GB		53.82	-3.05	145007
Blacksburg	US	Virginia	37.23	-80.41	44215
Blacktown	AU		-33.77	150.92	46942
Blackwall	GB		51.51	-0.00	19461
Blackwood	GB		51.67	-3.21	15476
Blagoevgrad	BG		42.01	23.10	67810
Blagoveshchensk	RU		50.28	127.53	225091
Blaine	US	Minnesota	45.16	-93.23	62124
Blainville	CA		45.67	-73.88	46493
Blanchardstown	IE		53.39	-6.38	16511
Blantyre	MW		-15.78	35.01	902588
Blantyre	GB		55.80	-4.09	17090
Blaydon-on-Tyne	GB		54.96	-1.71	15155
Blenheim	NZ		-41.52	173.95	29800
Bletchley	GB		51.99	-0.73	50193
Blida	DZ		36.47	2.83	331779
Blitar	ID		-8.10	112.17	161204
Bloemfontein	ZA		-29.12	26.21	556637
Blois	FR		47.59	1.33	53660
Bloomfield	US	New Jersey	40.81	-74.19	49120
Bloomfield	US	Connecticut	41.83	-72.73	21535
Bloomingdale	US	Florida	27.89	-82.24	22711
Bloomingdale	US	Illinois	41.96	-88.08	22254
Bloomington	US	Minnesota	44.84	-93.30	86435
Bloomington	US	Indiana	39.17	-86.53	84067
Bloomington	US	Illinois	40.48	-88.99	78292
Bloomington	US	California	34.07	-117.40	23851
Blora	ID		-6.97	111.42	51811
Bloxwich	GB		52.62	-2.00	40000
Blue Island	US	Illinois	41.66	-87.68	23652
Blue Mountains	AU		-33.71	150.33	78121
Blue Springs	US	Missouri	39.02	-94.28	54148
Bluffton	US	South Carolina	32.24	-80.86	16728
Blumenau	BR		-26.92	-49.07	361261
Blundell	CA		49.16	-123.16	18065
Blyth	GB		55.13	-1.51	37339
Blythe	US	California	33.61	-114.60	19208
Bnei Brak	IL		32.08	34.83	214444
Bo	SL		7.96	-11.74	233684
Boa Viagem	BR		-5.13	-39.73	50411
Boa Vista	BR		2.82	-60.67	419652
Boadilla del Monte	ES		40.41	-3.88	52626
Boardman	US	Ohio	41.02	-80.66	35376
Bobbili	IN		18.57	83.36	56819
Bobo-Dioulasso	BF		11.18	-4.29	904920
Bobruysk	BY		53.15	29.21	205502
Boca Del Mar	US	Florida	26.35	-80.15	24244
Boca Raton	US	Florida	26.36	-80.08	93235
Bocaue	PH		14.80	120.93	98649
Bocholt	DE		51.84	6.62	73943
Bochum	DE		51.48	7.22	385729
Bocoio	AO		-12.47	14.14	164685
Boconó	VE		9.25	-70.25	68990
Bodhan	IN		18.66	77.89	77573
Bodināyakkanūr	IN		10.01	77.35	75680
Bodmin	GB		50.47	-4.72	16909
Bodītī	ET		6.97	37.87	64900
Boende	CD		-0.28	20.88	50794
Bogale	MM		16.29	95.40	68938
Bogenhausen	DE		48.15	11.62	77542
Boghni	DZ		36.54	3.95	54666
Bognor Regis	GB		50.78	-0.68	63885
Bogor	ID		-6.59	106.79	1078351
Bogorodskoye	RU		55.81	37.72	103000
Bogotá	CO		4.61	-74.08	7674366
Bogra	BD		24.85	89.37	210000
Bohicon	BJ		7.18	2.07	93744
Bohodukhivskyi	UA		47.97	37.86	90600
Bohuniya	UA		50.28	28.61	147324
Boisbriand	CA		45.62	-73.83	26483
Boise	US	Idaho	43.61	-116.20	235684
Boituva	BR		-23.28	-47.67	62170
Bojnūrd	IR		37.47	57.33	192041
Bojonegoro	ID		-7.15	111.88	86568
Bokhtar	TJ		37.84	68.78	110800
Boksburg	ZA		-26.21	28.26	445168
Boké	GN		10.93	-14.29	63736
Bokāro	IN		23.67	86.15	564319
Bol	TD		13.47	14.71	51389
Bole	CN		44.89	82.07	235585
Bolenge	CD		0.00	18.22	79648
Bolgatanga	GH		10.79	-0.85	81958
Boli	CN		45.75	130.58	95260
Bolingbrook	US	Illinois	41.70	-88.07	74306
Bologna	IT		44.49	11.34	394843
Bolpur	IN		23.66	87.70	70998
Bolton	GB		53.58	-2.43	141331
Bolton	CA		43.88	-79.74	26795
Bolu	TR		40.74	31.61	184682
Bolvadin	TR		38.71	31.05	55870
Bolzano	IT		46.49	11.34	107436
Bom Despacho	BR		-19.74	-45.25	51737
Bom Jesus da Lapa	BR		-13.26	-43.42	65550
Boma	CD		-5.85	13.05	297009
Bon Air	US	Virginia	37.52	-77.56	16366
Bonan	CN		25.46	99.53	55685
Bonao	DO		18.94	-70.41	73269
Bondoukou	CI		8.04	-2.80	141568
Bondowoso	ID		-7.91	113.82	69783
Bonga	ET		7.29	36.24	56000
Bongabon	PH		15.63	121.14	69376
Bongaigaon	IN		26.48	90.56	67322
Bongor	TD		10.28	15.37	63699
Bonita Springs	US	Florida	26.34	-81.78	51704
Bonn	DE		50.73	7.10	330579
Bonney Lake	US	Washington	47.18	-122.19	19903
Bonnyrigg	GB		55.87	-3.11	18320
Bonon	CI		6.93	-6.05	119938
Bontang	ID		0.13	117.49	194606
Bonāb	IR		37.34	46.06	80359
Boone	US	North Carolina	36.22	-81.67	18156
Bootle	GB		53.47	-3.02	57791
Bor	RU		56.36	44.07	60647
Borama	SO		9.94	43.18	597842
Bordeaux	FR		44.84	-0.58	265328
Bordj Bou Arreridj	DZ		36.07	4.76	158812
Bordj el Bahri	DZ		36.79	3.25	52816
Bordj el Kiffan	DZ		36.75	3.19	123246
Bordon	GB		51.11	-0.86	20978
Borehamwood	GB		51.65	-0.28	36322
Borisoglebsk	RU		51.37	42.10	68597
Borivli	IN		19.23	72.86	609617
Borongan	PH		11.61	125.43	71431
Boronia	AU		-37.87	145.28	23607
Borough Park	US	New York	40.63	-74.00	149248
Borovichi	RU		58.39	33.92	56571
Borsad	IN		22.41	72.90	63377
Borshchahivka	UA		50.43	30.39	179900
Boryeong	KR		36.35	126.60	94191
Boryspil	UA		50.35	30.95	64117
Borås	SE		57.72	12.94	71700
Borāzjān	IR		29.27	51.22	110567
Borūjen	IR		31.97	51.29	57071
Borūjerd	IR		33.90	48.75	251958
Bosaso	SO		11.28	49.18	74287
Boshan	CN		36.48	117.83	153596
Bosque Saúde	BR		-23.61	-46.62	128469
Bossangoa	CF		6.49	17.46	55353
Bosse	UA		47.96	37.80	50000
Bossier City	US	Louisiana	32.52	-93.73	68094
Boston	US	Massachusetts	42.36	-71.06	653833
Boston	GB		52.98	-0.03	45339
Bostonia	US	California	32.81	-116.94	15379
Botad	IN		22.17	71.67	130327
Bothaville	ZA		-27.39	26.62	71934
Bothell	US	Washington	47.76	-122.21	42939
Bothell West	US	Washington	47.81	-122.24	16607
Botou	CN		38.07	116.57	63045
Botoşani	RO		47.75	26.67	90010
Botshabelo	ZA		-29.27	26.73	309714
Bottrop	DE		51.52	6.93	119909
Botucatu	BR		-22.89	-48.45	148130
Bou Saâda	DZ		35.21	4.17	111787
Bouaflé	CI		6.99	-5.74	104209
Bouaké	CI		7.69	-5.03	832371
Bouar	CF		5.93	15.60	71680
Boucherville	CA		45.59	-73.44	39062
Boudouaou	DZ		36.73	3.41	56398
Boufarik	DZ		36.57	2.91	57162
Bougouni	ML		11.42	-7.48	90234
Boulder	US	Colorado	40.01	-105.27	106803
Boulder City	US	Nevada	35.98	-114.83	15551
Boulogne-Billancourt	FR		48.84	2.24	108782
Boundiali	CI		9.52	-6.49	51803
Bountiful	US	Utah	40.89	-111.88	43784
Bourbonnais	US	Illinois	41.15	-87.89	18569
Bourges	FR		47.08	2.40	67987
Bournemouth	GB		50.72	-1.88	163600
Bouskoura	MA		33.45	-7.65	112501
Bouïra	DZ		36.37	3.90	68545
Bow	GB		51.53	-0.02	27720
Bowie	US	Maryland	38.94	-76.73	58025
Bowling Green	US	Kentucky	36.99	-86.44	63616
Bowling Green	US	Ohio	41.37	-83.65	31246
Bowmanville	CA		43.92	-78.68	39371
Bowthorpe	GB		52.64	1.22	20000
Boyeros	CU		23.01	-82.40	188593
Boyle Heights	US	California	34.03	-118.21	92785
Boynton Beach	US	Florida	26.53	-80.07	73966
Boyolali	ID		-7.53	110.60	59851
Bozeman	US	Montana	45.68	-111.04	43405
Bozhou	CN		33.88	115.77	1409436
Bozüyük	TR		39.91	30.04	55365
Bracebridge	CA		45.03	-79.32	16010
Bracken Ridge	AU		-27.32	153.03	16701
Bracknell	GB		51.41	-0.75	76103
Bradenton	US	Florida	27.50	-82.57	54437
Bradford	GB		53.79	-1.75	366187
Bradley	US	Illinois	41.14	-87.86	15617
Braga	PT		41.55	-8.42	193324
Bragança	BR		-1.05	-46.77	123082
Bragança Paulista	BR		-22.95	-46.54	176811
Brahmapur	IN		19.31	84.79	356598
Braintree	GB		51.88	0.55	53477
Braintree	US	Massachusetts	42.20	-71.00	37297
Brajarajnagar	IN		21.82	83.92	80403
Brakpan	ZA		-26.24	28.37	305692
Bramhall	GB		53.36	-2.17	17195
Brampton	CA		43.68	-79.77	656480
Brandenburg an der Havel	DE		52.42	12.55	59826
Brandon	US	Florida	27.94	-82.29	103483
Brandon	CA		49.85	-99.95	48859
Brandon	US	Mississippi	32.27	-89.99	23529
Branford	US	Connecticut	41.28	-72.82	29438
Brant	CA		43.13	-80.35	34415
Brantford	CA		43.13	-80.27	104688
Brasilandia	BR		-23.45	-46.69	243273
Brasília	BR		-15.78	-47.93	2207718
Brateyevo	RU		55.64	37.76	102000
Bratislava	SK		48.15	17.11	423737
Bratsk	RU		56.13	101.61	256600
Braunschweig	DE		52.27	10.53	244715
Braunstone	GB		52.62	-1.18	16850
Brawley	US	California	32.98	-115.53	25897
Bray	IE		53.20	-6.10	33512
Brazlândia	BR		-15.68	-48.20	55561
Brazzaville	CG		-4.27	15.28	1982000
Braşov	RO		45.65	25.61	253200
Brea	US	California	33.92	-117.90	41944
Breda	NL		51.59	4.78	184126
Bredbury	GB		53.42	-2.12	17040
Brejo da Madre de Deus	BR		-8.15	-36.37	51107
Brejo Santo	BR		-7.49	-38.99	51090
Bremen	DE		53.08	8.81	546501
Bremerhaven	DE		53.55	8.58	118610
Bremerton	US	Washington	47.57	-122.63	39520
Brenham	US	Texas	30.17	-96.40	16579
Brent	GB		51.55	-0.30	329100
Brent	US	Florida	30.47	-87.24	21804
Brentwood	US	New York	40.78	-73.25	60664
Brentwood	US	California	37.93	-121.70	58968
Brentwood	GB		51.62	0.31	52586
Brentwood	US	Tennessee	36.03	-86.78	41763
Brentwood	US	California	34.05	-118.47	33312
Brentwood Estates	US	Tennessee	36.03	-86.78	31279
Brescia	IT		45.54	10.21	200423
Brest	BY		52.11	23.72	347138
Brest	FR		48.39	-4.49	144899
Breves	BR		-1.68	-50.48	106968
Breña	PE		-12.06	-77.05	81909
Briarwood	US	New York	40.71	-73.82	53877
Brick	US	New Jersey	40.06	-74.14	76021
Bridgend	GB		51.51	-3.58	49597
Bridgeport	US	Connecticut	41.18	-73.19	147629
Bridgeport	US	Illinois	41.84	-87.65	33878
Bridgeton	US	New Jersey	39.43	-75.23	25031
Bridgetown	BB		13.11	-59.62	98511
Bridgeview	US	Illinois	41.75	-87.80	16407
Bridgewater	US	New Jersey	40.60	-74.65	44464
Bridgwater	GB		51.13	-3.00	41276
Bridlewood	CA		45.29	-75.86	24400
Bridlington	GB		54.08	-0.19	35154
Brierley Hill	GB		52.48	-2.12	28000
Brigham City	US	Utah	41.51	-112.02	18752
Brighouse	GB		53.70	-1.78	32872
Brighouse-City Centre	CA		49.17	-123.13	62855
Brighton	GB		50.83	-0.14	283870
Brighton	US	Massachusetts	42.35	-71.16	45977
Brighton	US	Colorado	39.99	-104.82	37585
Brighton	US	New York	43.15	-77.55	36609
Brighton	AU		-37.91	145.00	23252
Brighton Beach	US	New York	40.58	-73.96	31462
Brighton East	AU		-37.90	145.02	16757
Brighton Park	US	Illinois	41.82	-87.70	44202
Brightwood	US	District of Columbia	38.96	-77.03	17624
Brigittenau	AT		48.24	16.38	86967
Brikama	GM		13.27	-16.65	97233
Brindisi	IT		40.63	17.94	87141
Brisbane	AU		-27.47	153.03	2780063
Bristol	GB		51.46	-2.60	479024
Bristol	US	Connecticut	41.67	-72.95	60452
Bristol	US	Tennessee	36.60	-82.19	26666
Bristol	US	Rhode Island	41.68	-71.27	22795
Bristol	US	Virginia	36.60	-82.19	17141
Briton Ferry	GB		51.63	-3.82	35179
Brits	ZA		-25.63	27.78	122497
Brive-la-Gaillarde	FR		45.16	1.53	53466
Brixham	GB		50.39	-3.52	16693
Brixton	GB		51.47	-0.11	66300
Brno	CZ		49.20	16.61	379466
Brno střed	CZ		49.19	16.61	86685
Broad Ripple	US	Indiana	39.87	-86.14	17041
Broadmoor	CA		49.15	-123.13	23050
Broadstairs	GB		51.36	1.44	23283
Broadview Heights	US	Ohio	41.31	-81.69	19229
Brocklehurst	CA		50.71	-120.41	16713
Brockley	GB		51.46	-0.04	17156
Brockton	US	Massachusetts	42.08	-71.02	95314
Brockville	CA		44.59	-75.69	23886
Broken Arrow	US	Oklahoma	36.05	-95.79	106563
Broken Hill	AU		-31.97	141.45	17456
Bromma	SE		59.34	17.94	72000
Bromsgrove	GB		52.34	-2.06	34755
Brook Park	US	Ohio	41.40	-81.80	18809
Brookes Point	PH		8.77	117.84	76715
Brookfield	US	Wisconsin	43.06	-88.11	38025
Brookfield	US	Illinois	41.82	-87.85	18944
Brookhaven	US	Georgia	33.86	-84.34	51910
Brookhaven-Amesbury	CA		43.70	-79.49	17757
Brookings	US	South Dakota	44.31	-96.80	23657
Brooklin	CA		43.96	-78.96	25000
Brookline	US	Massachusetts	42.33	-71.12	58732
Brooklyn	US	New York	40.65	-73.95	2736074
Brooklyn Center	US	Minnesota	45.08	-93.33	30770
Brooklyn Heights	US	New York	40.70	-73.99	20256
Brooklyn Park	US	Minnesota	45.09	-93.36	79149
Broomfield	US	Colorado	39.92	-105.09	65065
Brossard	CA		45.45	-73.47	69575
Brough	GB		53.73	-0.57	19904
Brovary	UA		50.51	30.79	109806
Brownsburg	US	Indiana	39.84	-86.40	24996
Brownsville	US	Texas	25.90	-97.50	186738
Brownsville	US	New York	40.66	-73.92	74497
Brownsville	US	Florida	25.82	-80.24	15313
Brownwood	US	Texas	31.71	-98.99	19031
Broxburn	GB		55.93	-3.47	15970
Brugge	BE		51.21	3.22	118509
Brumado	BR		-14.20	-41.67	70510
Brunswick	US	Ohio	41.24	-81.84	34689
Brunswick	AU		-37.77	144.97	24896
Brunswick	US	Georgia	31.15	-81.49	16157
Brunswick	US	Maine	43.91	-69.97	15175
Brushy Creek	US	Texas	30.51	-97.74	21764
Brusque	BR		-27.10	-48.91	141385
Brussels	BE		50.85	4.35	1019022
Bryan	US	Texas	30.67	-96.37	82118
Bryansk	RU		53.27	34.32	427236
Bryant	US	Arkansas	34.60	-92.49	19986
Brymbo	GB		53.07	-3.07	18111
Bryn Mawr-Skyway	US	Washington	47.49	-122.24	15645
Brāhmanbāria	BD		23.97	91.11	264326
Brăila	RO		45.27	27.97	154686
Bucaramanga	CO		7.12	-73.12	581130
Buchanan	LR		5.88	-10.05	75854
Bucharest	RO		44.43	26.11	1877155
Bucheon-si	KR		37.50	126.78	850731
Buckeye	US	Arizona	33.37	-112.58	50876
Buckhall	US	Virginia	38.73	-77.43	16293
Buckingham	CA		45.59	-75.42	16685
Buckley	GB		53.17	-3.08	63576
Buda	HU		47.50	19.03	510108
Budapest	HU		47.50	19.04	1741041
Budapest II. kerület	HU		47.52	19.02	88729
Budapest III. kerület	HU		47.54	19.05	123723
Budapest IV. kerület	HU		47.56	19.09	98374
Budapest VIII. kerület	HU		47.49	19.07	82222
Budapest XI. kerület	HU		47.48	19.04	139049
Budapest XII. kerület	HU		47.49	19.01	56544
Budapest XIII. kerület	HU		47.53	19.08	113531
Budapest XIX. kerület	HU		47.45	19.15	61610
Budapest XV. kerület	HU		47.56	19.12	80218
Budapest XVI. kerület	HU		47.51	19.17	68484
Budapest XVII. kerület	HU		47.48	19.25	78250
Budapest XVIII. kerület	HU		47.44	19.18	93225
Budapest XX. kerület	HU		47.44	19.10	63371
Budapest XXI. kerület	HU		47.42	19.07	76339
Budapest XXII. kerület	HU		47.43	19.04	50499
Budaun	IN		28.04	79.13	161555
Buderim	AU		-26.68	153.06	28774
Budge Budge	IN		22.48	88.18	76837
Budta	PH		7.20	124.44	1273715
Buduburam	GH		5.52	-0.48	63217
Budyonnovsk	RU		44.78	44.17	67962
Buea	CM		4.15	9.24	140533
Buena Park	US	California	33.87	-118.00	83270
Buenaventura	CO		3.58	-77.00	432385
Buenaventura	CO		3.88	-77.03	240387
Buenaventura Lakes	US	Florida	28.34	-81.35	26079
Buenavista	MX		19.61	-99.17	216776
Buenavista	PH		8.98	125.41	70691
Bueng Kum	TH		13.79	100.67	145830
Buenos Aires	AR		-34.61	-58.38	2891082
Buffalo	US	New York	42.89	-78.88	258071
Buffalo	US	Minnesota	45.17	-93.87	16026
Buffalo Grove	US	Illinois	42.15	-87.96	41496
Bugulma	RU		54.54	52.80	91900
Buguma	NG		4.74	6.86	135404
Buguruslan	RU		53.66	52.44	53511
Buhe	CN		30.29	112.23	106347
Buin	CL		-33.73	-70.74	63419
Bujumbura	BI		-3.38	29.36	769317
Bukama	CD		-9.20	25.85	105530
Bukavu	CD		-2.49	28.84	816811
Bukhara	UZ		39.77	64.43	280187
Bukit Batok New Town	SG		1.36	103.76	158030
Bukit Bintang	MY		3.15	101.71	120529
Bukit Indah	MY		1.48	103.66	60000
Bukit Jalil	MY		3.05	101.68	200000
Bukit Merah Estate	SG		1.28	103.82	151250
Bukit Mertajam	MY		5.36	100.47	212329
Bukit Panjang New Town	SG		1.38	103.76	138050
Bukit Rahman Putra	MY		3.22	101.56	607000
Bukit Tengah	MY		5.35	100.44	54416
Bukit Timah	SG		1.33	103.79	85900
Bukittinggi	ID		-0.31	100.37	121028
Bukoba	TZ		-1.33	31.81	144938
Bulacan	PH		14.79	120.88	83101
Bulandshahr	IN		28.40	77.86	198612
Bulaon	PH		15.08	120.66	131818
Bulawayo	ZW		-20.15	28.58	665952
Buldāna	IN		20.53	76.18	67431
Bullhead City	US	Arizona	35.15	-114.57	39445
Buluan	PH		6.72	124.80	60931
Bulungu	CD		-4.54	18.60	81393
Bumba	CD		2.19	22.47	154586
Bunamwaya	UG		0.25	32.56	413400
Bunawan	PH		8.17	125.99	50999
Bunbury	AU		-33.33	115.64	76452
Bunda	TZ		-2.02	33.87	182970
Bundaberg	AU		-24.87	152.35	73747
Bundoora	AU		-37.70	145.06	28068
Bungoma	KE		0.56	34.56	68031
Buni	PK		36.27	72.26	50000
Bunia	CD		1.56	30.25	399282
Bunkyo	JP		35.53	139.42	240069
Bununka Kunda	GM		13.43	-16.69	66449
Burao	SO		9.52	45.53	99270
Burauen	PH		10.98	124.89	54635
Buraydah	SA		26.33	43.97	745353
Burayu	ET		9.04	38.66	101400
Burbank	US	California	34.18	-118.31	105319
Burbank	US	Illinois	41.73	-87.78	29128
Burdur	TR		37.72	30.29	95436
Burewala	PK		30.17	72.65	361664
Burgas	BG		42.51	27.47	210646
Burgess Hill	GB		50.96	-0.13	30635
Burgos	ES		42.34	-3.70	176418
Burhānpur	IN		21.31	76.23	210886
Burien	US	Washington	47.47	-122.35	50467
Buriticupu	BR		-4.32	-46.45	55499
Burke	US	Virginia	38.79	-77.27	41055
Burleson	US	Texas	32.54	-97.32	43625
Burlingame	US	California	37.58	-122.37	30459
Burlington	CA		43.39	-79.84	186948
Burlington	US	North Carolina	36.10	-79.44	52472
Burlington	US	Vermont	44.48	-73.21	42452
Burlington	US	Iowa	40.81	-91.11	25410
Burlington	US	Massachusetts	42.50	-71.20	24498
Burlington	US	Kentucky	39.03	-84.72	15926
Burnaby	CA		49.27	-122.95	249125
Burngreave	GB		53.39	-1.46	27481
Burnham-on-Sea	GB		51.24	-3.00	23325
Burnie	AU		-41.06	145.90	20417
Burnley	GB		53.80	-2.23	149422
Burnsville	US	Minnesota	44.77	-93.28	61481
Burntwood	GB		52.68	-1.93	29244
Bursa	TR		40.20	29.06	3101833
Burton	US	Michigan	43.00	-83.62	28788
Burton upon Trent	GB		52.81	-1.64	122199
Burwood	AU		-33.88	151.10	18224
Burwood	AU		-37.85	145.12	15147
Bury	GB		53.60	-2.30	61044
Bury St Edmunds	GB		52.25	0.71	41280
Burzaco	AR		-34.83	-58.40	98859
Burām	SD		10.86	25.16	65473
Burāri	IN		28.76	77.20	146190
Busan	KR		35.10	129.03	3285147
Buseresere	TZ		-3.05	31.89	52870
Bushehr	IR		28.97	50.84	165377
Bushey	GB		51.64	-0.36	28416
Bushwick	US	New York	40.69	-73.92	112620
Busia	KE		0.46	34.11	71886
Busia	UG		0.47	34.09	64900
Business Bay	AE		25.19	55.27	191000
Busselton	AU		-33.65	115.35	27233
Bustleton	US	Pennsylvania	40.08	-75.03	32655
Busto Arsizio	IT		45.61	8.85	83405
Bustos	PH		14.96	120.92	80565
Buta	CD		2.79	24.73	80751
Butajīra	ET		8.12	38.37	89800
Butanta	BR		-23.57	-46.73	123748
Butare	RW		-2.60	29.74	62823
Butembo	CD		0.14	29.29	286242
Buthidaung Town	MM		20.88	92.53	55545
Butte	US	Montana	46.00	-112.53	34190
Butterworth	MY		5.40	100.36	107591
Butterworth	ZA		-32.33	28.15	53086
Butuan	PH		8.95	125.54	309709
Butwāl	NP		27.69	83.45	195054
Buxar	IN		25.58	83.98	102861
Buxton	GB		53.26	-1.91	20048
Buyeo	KR		36.27	126.91	59823
Buynaksk	RU		42.82	47.13	62689
Buzhuang	CN		36.91	119.56	53474
Buzuluk	RU		52.78	52.26	87714
Buzău	RO		45.15	26.83	103481
Buíque	BR		-8.62	-37.16	54425
Buôn Hồ	VN		12.95	108.30	127920
Buôn Ma Thuột	VN		12.67	108.04	434256
Bwizibwera	UG		-0.59	30.63	79157
Byasanagar	IN		20.96	86.13	56946
Bydgoszcz	PL		53.12	18.01	330038
Byford	AU		-32.22	116.01	18878
Bytom	PL		50.35	18.93	189186
Bârlad	RO		46.23	27.67	67818
Béchar	DZ		31.62	-2.22	165241
Bégoua	CF		4.45	18.53	264067
Béja	TN		36.73	9.18	61568
Béjaïa	DZ		36.76	5.08	176139
Békéscsaba	HU		46.68	21.10	59732
Béziers	FR		43.34	3.21	74081
Bình Minh	VN		10.07	105.82	94862
Bình Thạnh	VN		10.81	106.71	552164
Bình Thủy	VN		10.07	105.74	113565
Büyükçekmece	TR		41.02	28.59	163140
Bābol	IR		36.55	52.68	202796
Bāghestān	IR		35.65	51.13	83934
Bāli	IN		22.65	88.34	296973
Bālurghāt	IN		25.22	88.78	153279
Bālāghāt	IN		21.82	80.19	84261
Bāmyān	AF		34.82	67.83	61863
Bānda	IN		25.48	80.33	152218
Bāndarban	BD		22.20	92.22	495272
Bāneh	IR		36.00	45.89	110218
Bāngarda Chhota	IN		22.74	75.81	64213
Bānkura	IN		23.23	87.07	133966
Bānsbāria	IN		22.95	88.40	108474
Bānswāra	IN		23.54	74.44	101017
Bāpatla	IN		15.90	80.47	70777
Bāprola	IN		28.64	77.01	52744
Bāqershahr	IR		35.53	51.40	65388
Bāramūla	IN		34.21	74.34	77276
Bārdoli	IN		21.12	73.11	60821
Bārh	IN		25.48	85.71	61470
Bāri	IN		26.65	77.62	62721
Bārmer	IN		25.75	71.39	96225
Bāruni	IN		25.48	85.97	84888
Bārākpur	IN		22.77	88.36	148174
Bārāmati	IN		18.15	74.58	54415
Bārān	IN		25.10	76.52	117992
Bārāsat	IN		22.72	88.48	298127
Bāzār-e Yakāwlang	AF		34.74	66.97	65000
Bāzārak	AF		35.31	69.52	65000
Bălţi	MD		47.76	27.93	125000
Będzin	PL		50.33	19.13	58236
Bījār	IR		35.87	47.61	50014
Bīna	IN		24.17	78.19	64529
Bīrjand	IR		32.87	59.22	196982
Bīsalpur	IN		28.29	79.80	68355
Būkān	IR		36.52	46.21	193501
Būlāq Abū al ‘Ilā	EG		30.06	31.23	51741
Būmahen	IR		35.73	51.87	79034
Būndi	IN		25.44	75.64	104919
Būsh	EG		29.15	31.13	136441
Bạc Liêu	VN		9.29	105.73	156110
Bạch Mai	VN		20.98	105.83	91308
Bảo Lộc	VN		11.55	107.81	170920
Bắc Giang	VN		21.27	106.19	450000
Bắc Ninh	VN		21.19	106.08	287658
Bắc Quang	VN		22.48	104.87	118690
Bắc Từ Liêm	VN		21.07	105.75	340605
Bến Cát	VN		11.15	106.60	364578
Bến Tre	VN		10.24	106.38	124449
Bỉm Sơn	VN		20.08	105.86	53754
Bồ Đề	VN		21.06	105.87	120028
Caacupé	PY		-25.39	-57.14	56864
Caaguazú	PY		-25.47	-56.02	54808
Cabanatuan City	PH		15.49	120.97	343672
Cabedelo	BR		-6.98	-34.83	66519
Cabimas	VE		10.40	-71.45	351736
Cabinda	AO		-5.56	12.19	550000
Cabo de Santo Agostinho	BR		-8.29	-35.03	216969
Cabo Frio	BR		-22.89	-42.03	238166
Cabo San Lucas	MX		22.89	-109.91	202694
Caboolture	AU		-27.08	152.95	26341
Cabot	US	Arkansas	34.97	-92.02	25587
Cabramatta	AU		-33.90	150.93	21634
Cabudare	VE		10.03	-69.26	102686
Cabudwaaq	SO		6.25	46.22	120000
Cabuyao	PH		14.27	121.13	308745
Cachoeira do Sul	BR		-30.04	-52.89	80070
Cachoeiras de Macacu	BR		-22.46	-42.65	59837
Cachoeirinha	BR		-23.45	-46.66	143366
Cachoeirinha	BR		-29.95	-51.09	136258
Cachoeiro de Itapemirim	BR		-20.85	-41.11	187019
Cacoal	BR		-11.44	-61.45	86887
Cacuaco	AO		-8.78	13.37	146867
Cacém	PT		38.77	-9.30	93982
Cadereyta	MX		25.58	-99.98	67994
Cadereyta Jiménez	MX		25.59	-100.00	68111
Cadiz	PH		10.95	123.29	129053
Cadiz	ES		36.53	-6.29	116979
Caen	FR		49.19	-0.36	110624
Caerphilly	GB		51.57	-3.22	31060
Caetité	BR		-14.07	-42.48	52012
Cafunfo	AO		-8.77	18.00	90000
Cagayan de Oro	PH		8.48	124.65	741617
Cagliari	IT		39.23	9.12	149257
Cagua	VE		10.19	-67.46	119033
Caguas	PR		18.23	-66.05	86804
Cahama	AO		-16.29	14.31	70061
Cai Lậy	VN		10.40	106.12	143050
Caicara del Orinoco	VE		7.64	-66.17	67277
Caicó	BR		-6.46	-37.10	61146
Caidian	CN		30.58	114.03	71891
Caieiras	BR		-23.36	-46.74	102775
Cainta	PH		14.58	121.12	283172
Cairns	AU		-16.92	145.77	153075
Cairo	EG		30.06	31.25	9606916
Cajamar	BR		-23.36	-46.88	92689
Cajamarca	PE		-7.16	-78.50	201329
Cajazeiras	BR		-6.89	-38.56	63239
Cajicá	CO		4.92	-74.03	54111
Calabanga	PH		13.71	123.21	88918
Calabar	NG		4.96	8.33	540000
Calabasas	US	California	34.16	-118.64	23058
Calabozo	VE		8.92	-67.43	168605
Calais	FR		50.95	1.86	74433
Calama	CL		-22.46	-68.92	166334
Calamba	PH		14.21	121.17	575046
Calamvale	AU		-27.62	153.05	16927
Calapan	PH		13.41	121.18	66008
Calarcá	CO		4.53	-75.64	79569
Calasiao	PH		16.01	120.36	100686
Calauag	PH		13.96	122.29	68999
Calauan	PH		14.15	121.32	89670
Calbayog City	PH		12.07	124.60	67921
Caldas	CO		6.09	-75.64	82234
Caldas Novas	BR		-17.74	-48.63	98622
Caldwell	US	Idaho	43.66	-116.69	51686
Caledon	CA		43.87	-79.99	76581
Caledonia	US	Wisconsin	42.81	-87.92	24684
Caleta Olivia	AR		-46.45	-67.52	56310
Calexico	US	California	32.68	-115.50	40053
Calgary	CA		51.05	-114.09	1306784
Calhoun	US	Georgia	34.50	-84.95	16309
Cali	CO		3.43	-76.52	2392877
Callao	PE		-12.05	-77.13	1226200
Calne	GB		51.44	-2.01	17274
Caloocan	PH		14.65	120.97	1712945
Caloundra	AU		-26.80	153.12	96305
Caltanissetta	IT		37.49	14.06	62797
Calumbo	AO		-9.15	13.42	652270
Calumet City	US	Illinois	41.62	-87.53	37031
Calumpit	PH		14.92	120.77	122187
Calverton	US	Maryland	39.06	-76.94	17724
Calvià	ES		39.57	2.51	51774
Cam Ranh	VN		11.92	109.16	146771
Camacupa	AO		-12.02	17.48	59000
Camagüey	CU		21.38	-77.92	347562
Camama	AO		-8.94	13.27	667094
Camaquã	BR		-30.85	-51.81	62200
Camaragibe	BR		-8.02	-34.98	155771
Camarillo	US	California	34.22	-119.04	67608
Camas	US	Washington	45.59	-122.40	21846
Camayenne	GN		9.54	-13.69	1871242
Camaçari	BR		-12.70	-38.32	188758
Camberley	GB		51.34	-0.74	30155
Camberwell	AU		-37.84	145.07	21965
Camboriú	BR		-27.03	-48.65	85105
Camborne	GB		50.21	-5.30	20450
Cambria Heights	US	New York	40.69	-73.74	20287
Cambridge	GB		52.20	0.12	145674
Cambridge	CA		43.36	-80.31	129920
Cambridge	US	Massachusetts	42.38	-71.11	110402
Cambridge	NZ		-37.88	175.44	15192
Cambuslang	GB		55.81	-4.16	30790
Cambé	BR		-23.28	-51.28	107208
Camden	US	New Jersey	39.93	-75.12	76119
Camden Town	GB		51.54	-0.14	26122
Cameron Park	US	California	38.67	-120.99	18228
Cametá	BR		-2.24	-49.50	134184
Camocim	BR		-2.90	-40.84	62326
Camp Springs	US	Maryland	38.80	-76.91	19096
Campana	AR		-34.16	-58.96	86860
Campbell	US	California	37.29	-121.95	41117
Campbell River	CA		50.02	-125.24	33430
Campeche	MX		19.84	-90.52	220389
Campina Grande	BR		-7.23	-35.88	348936
Campinas	BR		-22.91	-47.06	1031554
Campiña	ES		38.22	-2.98	67904
Campo Belo	BR		-23.63	-46.67	71058
Campo Belo	BR		-20.90	-45.28	52277
Campo Bom	BR		-29.68	-51.05	62886
Campo di Marte	IT		43.78	11.28	88588
Campo Formoso	BR		-10.51	-40.32	71377
Campo Grande	BR		-20.44	-54.65	906092
Campo Grande	BR		-23.67	-46.69	115925
Campo Largo	BR		-25.46	-49.53	136327
Campo Limpo	BR		-23.64	-46.77	236162
Campo Limpo Paulista	BR		-23.21	-46.78	77632
Campo Mourão	BR		-24.04	-52.38	99432
Campo Novo do Parecis	BR		-13.68	-57.89	50033
Campos do Jordão	BR		-22.74	-45.59	52405
Campos dos Goytacazes	BR		-21.75	-41.33	483540
Campsie	AU		-33.91	151.10	24487
Camrose	CA		53.02	-112.84	20405
Camucuio	AO		-14.11	13.24	66112
Canarsie	US	New York	40.64	-73.90	87366
Canary Wharf	GB		51.51	-0.02	73390
Canaã dos Carajás	BR		-6.52	-49.85	77079
Canberra	AU		-35.28	149.13	367752
Canby	US	Oregon	45.26	-122.69	17271
Cancún	MX		21.17	-86.85	888797
Candeias	BR		-12.67	-38.55	72382
Candelaria	PH		13.93	121.42	137933
Candiac	CA		45.38	-73.52	15947
Candler-McAfee	US	Georgia	33.73	-84.27	23025
Cangaiba	BR		-23.50	-46.52	141172
Cangandala	AO		-9.78	16.43	52220
Cangzhou	CN		38.31	116.85	527681
Canindé	BR		-4.36	-39.31	74174
Cannes	FR		43.55	7.01	74545
Canning Town	GB		51.51	0.02	42667
Canning Vale	AU		-32.06	115.92	34504
Cannock	GB		52.69	-2.03	86121
Canoas	BR		-29.92	-51.18	328291
Canoga Park	US	California	34.20	-118.60	60578
Canoinhas	BR		-26.18	-50.39	55016
Cantaura	VE		9.31	-64.36	68885
Canterbury	GB		51.28	1.08	55087
Canton	US	Michigan	42.31	-83.48	86825
Canton	US	Ohio	40.80	-81.38	71885
Canton	US	Georgia	34.24	-84.49	25469
Canton	US	Massachusetts	42.16	-71.14	21679
Cantonment	US	Florida	30.61	-87.34	26493
Canvey Island	GB		51.52	0.58	38170
Canyon Country	US	California	34.42	-118.47	59530
Canyon Lake	US	Texas	29.88	-98.26	21262
Cao Bằng	VN		22.67	106.26	73549
Cao Lãnh	VN		10.46	105.63	211912
Caohe	CN		30.23	115.43	67370
Caoqiao	CN		34.34	118.11	65243
Caotun	TW		23.98	120.69	96838
Cap-Haïtien	HT		19.76	-72.20	134815
Capalaba	AU		-27.54	153.20	18002
Capanema	BR		-1.20	-47.18	70394
Capao Redondo	BR		-23.67	-46.78	270767
Capas	PH		15.33	120.59	162724
Cape Coast	GH		5.11	-1.25	212426
Cape Coral	US	Florida	26.56	-81.95	175229
Cape Girardeau	US	Missouri	37.31	-89.52	39462
Cape Town	ZA		-33.93	18.42	4772846
Capelle aan den IJssel	NL		51.93	4.58	65255
Capiatá	PY		-25.36	-57.45	198553
Capitol Hill	US	District of Columbia	38.89	-77.00	15056
Capitol Riverfront	US	District of Columbia	38.88	-77.00	18874
Capitão Poço	BR		-1.75	-47.06	56506
Capivari	BR		-23.00	-47.51	50068
Capão da Canoa	BR		-29.75	-50.01	63594
Carabanchel	ES		40.39	-3.72	253678
Caracas	VE		10.49	-66.88	3000000
Caraguatatuba	BR		-23.62	-45.41	123389
Carapicuíba	BR		-23.52	-46.84	386984
Caratinga	BR		-19.79	-42.14	87360
Carazinho	BR		-28.28	-52.79	61804
Carbondale	US	Illinois	37.73	-89.22	26399
Cardiff	GB		51.48	-3.18	372089
Cardona	PH		14.49	121.23	51493
Carey	CA		48.47	-123.39	18405
Cariacica	BR		-20.26	-40.42	353491
Cariboo	CA		49.25	-122.88	22780
Carindale	AU		-27.51	153.10	15418
Caringin	ID		-6.71	106.82	91845
Carletonville	ZA		-26.36	27.40	182304
Carlingford	AU		-33.78	151.05	24131
Carlisle	GB		54.90	-2.94	78470
Carlisle	US	Pennsylvania	40.20	-77.19	19143
Carlow	IE		52.84	-6.93	27351
Carlsbad	US	California	33.16	-117.35	114746
Carlsbad	US	New Mexico	32.42	-104.23	28957
Carlton	AU		-37.80	144.97	16055
Carmarthen	GB		51.86	-4.31	15854
Carmel	US	Indiana	39.98	-86.12	88713
Carmichael	US	California	38.62	-121.33	61762
Carmona	PH		14.31	121.06	112140
Carnegie	AU		-37.89	145.06	17909
Carney	US	Maryland	39.39	-76.52	29941
Carnot	CF		4.94	15.88	129032
Carol City	US	Florida	25.94	-80.25	63031
Carol Stream	US	Illinois	41.91	-88.13	40356
Carolina	PR		18.38	-65.96	170404
Caroline Springs	AU		-37.74	144.74	24488
Carora	VE		10.17	-70.08	121741
Carpentersville	US	Illinois	42.12	-88.26	38512
Carpi	IT		44.78	10.88	71148
Carpina	BR		-7.85	-35.25	83205
Carrao	BR		-23.55	-46.54	84397
Carrara	IT		44.08	10.10	58666
Carrboro	US	North Carolina	35.91	-79.08	21156
Carrefour	HT		18.53	-72.40	511345
Carrickfergus	GB		54.72	-5.81	29208
Carrigaline	IE		51.81	-8.40	18239
Carrollton	US	Texas	32.95	-96.89	133168
Carrollton	US	Georgia	33.58	-85.08	26203
Carrollwood	US	Florida	28.05	-82.49	33365
Carrollwood Village	US	Florida	28.07	-82.52	40949
Carrum Downs	AU		-38.10	145.17	21976
Carshalton	GB		51.37	-0.17	45525
Carson	US	California	33.83	-118.28	93281
Carson City	US	Nevada	39.16	-119.77	58639
Cartagena	CO		10.40	-75.49	914552
Cartagena	ES		37.60	-0.98	213943
Cartago	CO		4.75	-75.91	134972
Carteret	US	New Jersey	40.58	-74.23	24170
Cartersville	US	Georgia	34.17	-84.80	20319
Carterton	GB		51.76	-1.59	15680
Cartierville	CA		45.53	-73.70	34667
Caruaru	BR		-8.28	-35.98	402290
Cary	US	North Carolina	35.79	-78.78	159769
Cary	US	Illinois	42.21	-88.24	17965
Carúpano	VE		10.67	-63.25	167187
Casa de Oro-Mount Helix	US	California	32.76	-116.97	18762
Casa Grande	US	Arizona	32.88	-111.76	51460
Casa Nova	BR		-9.17	-40.98	72086
Casa Verde	BR		-23.50	-46.66	80536
Casablanca	MA		33.59	-7.61	3665954
Casas Adobes	US	Arizona	32.32	-111.00	66795
Cascavel	BR		-24.96	-53.46	257172
Cascavel	BR		-4.13	-38.24	72720
Caserta	IT		41.07	14.33	72844
Casoria	IT		40.91	14.29	73918
Casper	US	Wyoming	42.87	-106.31	60285
Casselberry	US	Florida	28.68	-81.33	27056
Castaic	US	California	34.49	-118.62	19015
Castanhal	BR		-1.29	-47.93	192256
Castelar	AR		-34.65	-58.64	107786
Castellammare di Stabia	IT		40.70	14.49	66164
Castelldefels	ES		41.28	1.97	66375
Castelló de la Plana	ES		39.99	-0.05	171857
Castle Hill	AU		-33.73	151.00	39284
Castle Rock	US	Colorado	39.37	-104.86	55591
Castleford	GB		53.73	-1.36	45106
Castlereagh	GB		54.57	-5.88	56679
Castlewood	US	Colorado	39.58	-104.90	25271
Castries	LC		14.00	-61.01	20000
Castro	BR		-24.79	-50.01	73075
Castro Valley	US	California	37.69	-122.09	61388
Castrop-Rauxel	DE		51.56	7.31	77924
Casula	AU		-33.95	150.90	15695
Catacamas	HN		14.85	-85.89	140548
Catacaos	PE		-5.27	-80.68	57304
Cataguases	BR		-21.39	-42.70	66261
Catalina Foothills	US	Arizona	32.30	-110.92	50796
Catalão	BR		-18.17	-47.95	114427
Catamarca	AR		-28.47	-65.79	159139
Catanduva	BR		-21.14	-48.97	115791
Catania	IT		37.49	15.07	311584
Catanzaro	IT		38.88	16.60	78970
Catarman	PH		12.50	124.64	97738
Catbalogan	PH		11.78	124.89	107896
Catchiungo	AO		-12.57	16.23	120677
Caterham	GB		51.28	-0.08	20957
Catford	GB		51.44	-0.02	44905
Cathedral City	US	California	33.78	-116.47	53826
Catia La Mar	VE		10.61	-67.03	106822
Catonsville	US	Maryland	39.27	-76.73	41567
Catumbela	AO		-12.43	13.55	95034
Caucagüito	VE		10.49	-66.74	52556
Caucaia	BR		-3.74	-38.65	355679
Caucasia	CO		7.99	-75.19	58034
Caulfield North	AU		-37.87	145.02	16903
Cava Dè Tirreni	IT		40.70	14.71	53130
Cave Spring	US	Virginia	37.23	-80.01	24922
Cavite City	PH		14.48	120.90	115932
Caxias	BR		-4.86	-43.36	156973
Caxias do Sul	BR		-29.17	-51.18	381270
Caxito	AO		-8.58	13.66	55000
Cayenne	GF		4.94	-52.33	61550
Cazenga	AO		-8.84	13.28	394170
Caála	AO		-12.85	15.56	130000
Caçador	BR		-26.78	-51.02	73720
Caçapava	BR		-23.10	-45.71	96202
Cañon City	US	Colorado	38.44	-105.24	16400
Ceará-Mirim	BR		-5.63	-35.43	79115
Cebu City	PH		10.32	123.89	965332
Cedar City	US	Utah	37.68	-113.06	30184
Cedar Falls	US	Iowa	42.53	-92.45	41255
Cedar Hill	US	Texas	32.59	-96.96	48507
Cedar Park	US	Texas	30.51	-97.82	65945
Cedar Rapids	US	Iowa	42.01	-91.64	130405
Ceilândia	BR		-15.81	-48.13	287023
Cela	AO		-11.42	15.12	90000
Celaya	MX		20.52	-100.81	340387
Celbridge	IE		53.34	-6.54	20288
Celina	US	Texas	33.32	-96.78	64427
Celle	DE		52.62	10.08	71010
Centennial	US	Colorado	39.58	-104.88	109741
Center City	US	Pennsylvania	39.95	-75.16	57239
Center Point	US	Alabama	33.65	-86.68	16655
Centereach	US	New York	40.86	-73.10	31578
Centerville	US	Ohio	39.63	-84.16	23882
Centerville	US	Utah	40.92	-111.87	16877
Central	US	Louisiana	30.55	-91.04	28295
Central 14th Street / Spring Road	US	District of Columbia	38.94	-77.03	25899
Central City	US	Arizona	33.44	-112.06	58161
Central Coast	AU		-33.43	151.37	346596
Central Coquitlam	CA		49.26	-122.84	15480
Central Falls	US	Rhode Island	41.89	-71.39	19303
Central Islip	US	New York	40.79	-73.20	34450
Central Lonsdale	CA		49.33	-123.07	18485
Central Point	US	Oregon	42.38	-122.92	17995
Central Saanich	CA		48.57	-123.42	17385
Centralia	US	Washington	46.72	-122.95	16753
Centralniy	RU		59.93	30.36	214625
Centretown	CA		45.42	-75.70	25687
Centreville	US	Virginia	38.84	-77.43	71135
Centro	ES		28.13	-15.43	88546
Centro Habana	CU		23.13	-82.37	158151
Centurion	ZA		-25.86	28.19	236580
Cepu	ID		-7.15	111.59	55055
Cerdanyola del Vallès	ES		41.49	2.14	58747
Ceres	US	California	37.59	-120.96	47963
Cereté	CO		8.88	-75.79	94935
Cergy	FR		49.04	2.08	57576
Cergy-Pontoise	FR		49.04	2.08	183430
Cerignola	IT		41.27	15.90	54056
Cerritos	US	California	33.86	-118.06	49975
Cerro	CU		23.11	-82.38	132351
Cerro de Pasco	PE		-10.67	-76.25	58899
Cesena	IT		44.14	12.24	97137
Cessnock	AU		-32.83	151.36	23211
Ceuta	ES		35.89	-5.32	83179
Ceyhan	TR		37.02	35.82	96303
Chacao	VE		10.50	-66.85	64609
Chadderton	GB		53.54	-2.14	37602
Chaeryŏng-ni	KP		38.74	125.23	125631
Chaeryŏng-ŭp	KP		38.40	125.62	53330
Chagni	ET		10.96	36.50	52300
Chaguanas	TT		10.52	-61.42	67433
Chaigou	CN		36.25	119.62	79043
Chaihe	CN		44.76	129.68	67963
Chaiyaphum	TH		15.81	102.03	58350
Chak Jhumra	PK		31.57	73.18	385169
Chake Chake	TZ		-5.25	39.77	52047
Chakradharpur	IN		22.68	85.63	56531
Chakwal	PK		32.93	72.85	101200
Chakwama	NG		11.56	9.66	200000
Chalco	MX		19.26	-98.90	168720
Chalfont Saint Peter	GB		51.61	-0.56	20059
Chalisgaon	IN		20.46	75.02	97551
Chalk Farm	GB		51.54	-0.15	24977
Chalkída	GR		38.46	23.60	59125
Challakere	IN		14.32	76.65	55194
Chalmette	US	Louisiana	29.94	-89.97	16751
Chaman	PK		30.92	66.45	130139
Chamartín	ES		40.46	-3.68	140000
Chambersburg	US	Pennsylvania	39.94	-77.66	20691
Chamberí	ES		40.43	-3.70	145934
Chamblee	US	Georgia	33.89	-84.30	28244
Chambly	CA		45.45	-73.28	22608
Chambéry	FR		45.57	5.92	61640
Champaign	US	Illinois	40.12	-88.24	86096
Champigny-sur-Marne	FR		48.82	2.49	76726
Champlin	US	Minnesota	45.19	-93.40	23894
Chamrajnagar	IN		11.92	76.94	69875
Chandannagar	IN		22.86	88.37	180623
Chandigarh	IN		30.74	76.79	970602
Chandler	US	Arizona	33.31	-111.84	260828
Chanduasi	IN		28.45	78.78	112635
Chang-hua	TW		24.07	120.56	226564
Changam-ch’on	KP		40.61	128.78	207299
Changanācheri	IN		9.44	76.54	51430
Changbai	CN		41.42	128.20	58266
Changcheng	CN		36.09	119.45	63208
Changchun	CN		43.88	125.32	4714996
Changde	CN		29.03	111.70	1457419
Changhua	TW		24.07	120.55	226564
Changji	CN		44.01	87.30	198776
Changle	CN		36.71	118.83	259161
Changle	CN		21.83	109.42	62763
Changleng	CN		28.70	115.82	56429
Changli	CN		39.71	119.16	64476
Changling	CN		44.27	123.98	55841
Changning	CN		31.22	121.42	694900
Changning	CN		28.58	104.92	81248
Changnyeong	KR		35.54	128.50	74668
Changping	CN		40.22	116.23	93174
Changqing	CN		36.56	116.73	82598
Changsha	CN		28.20	112.97	3093980
Changsha	CN		22.38	112.68	688242
Changshu	CN		31.65	120.74	1677050
Changtu	CN		42.78	124.10	71284
Changwon	KR		35.23	128.68	1025702
Changyi	CN		36.85	119.39	302072
Changyuan	CN		29.40	105.59	186653
Changzheng	CN		31.24	121.37	229925
Changzhi	CN		36.18	113.11	1214940
Changzhi	CN		35.21	111.74	699514
Changzhou	CN		31.77	119.95	3290918
Chanhassen	US	Minnesota	44.86	-93.53	25332
Chaniá	GR		35.51	24.03	53910
Channapatna	IN		12.65	77.21	71942
Channelview	US	Texas	29.78	-95.11	38289
Chanthaburi	TH		12.61	102.10	99819
Chantilly	US	Virginia	38.89	-77.43	23039
Chaohu	CN		31.60	117.87	138463
Chaoyang	CN		41.57	120.46	410005
Chaoyang	CN		42.66	126.03	75347
Chaozhou	CN		23.65	116.62	1750945
Chaozhou	TW		22.55	120.54	53338
Chapadinha	BR		-3.74	-43.36	81386
Chapayevsk	RU		52.98	49.71	70147
Chapecó	BR		-27.10	-52.62	160157
Chapel Allerton	GB		53.83	-1.54	18206
Chapel Hill	US	North Carolina	35.91	-79.06	59568
Chapeltown	GB		53.47	-1.47	23056
Charallave	VE		10.24	-66.86	129182
Charikar	AF		35.01	69.17	53676
Charkhi Dādri	IN		28.59	76.27	56337
Charleroi	BE		50.41	4.44	200132
Charlesbourg	CA		46.90	-71.31	82870
Charleston	US	South Carolina	32.78	-79.93	132609
Charleston	US	West Virginia	38.35	-81.63	46838
Charleston	US	Illinois	39.50	-88.18	21196
Charlestown	US	Massachusetts	42.38	-71.06	20397
Charleville-Mézières	FR		49.77	4.72	52415
Charlotte	US	North Carolina	35.23	-80.84	911311
Charlotte Amalie	VI		18.34	-64.93	20000
Charlottenburg	DE		52.52	13.28	129359
Charlottesville	US	Virginia	38.03	-78.48	46597
Charlottetown	CA		46.23	-63.13	38809
Charsadda	PK		34.15	71.74	120170
Chas	IN		23.64	86.17	141640
Chaska	US	Minnesota	44.79	-93.60	25199
Chatham	GB		51.38	0.53	80596
Chatham	CA		42.41	-82.18	43550
Chatham	US	Illinois	41.74	-87.61	31392
Chatswood	AU		-33.80	151.18	25140
Chatsworth	US	California	34.26	-118.60	41255
Chattanooga	US	Tennessee	35.05	-85.31	181099
Chattogram	BD		22.34	91.83	3920222
Chatuchak	TH		13.83	100.56	160906
Chauk	MM		20.90	94.82	90870
Chaumu	IN		27.17	75.72	64417
Chautārā	NP		27.78	85.71	51347
Chaykovskiy	RU		56.76	54.11	86712
Cheadle Hulme	GB		53.38	-2.19	28952
Cheboksary	RU		56.13	47.25	492331
Cheektowaga	US	New York	42.90	-78.75	75178
Chegutu	ZW		-18.13	30.14	65800
Chekhov	RU		55.15	37.46	75643
Chelghoum el Aïd	DZ		36.16	6.17	54495
Chelmsford	GB		51.74	0.47	111511
Chelmsford	US	Massachusetts	42.60	-71.37	33925
Chelsea	GB		51.49	-0.17	60000
Chelsea	US	Massachusetts	42.39	-71.03	39398
Cheltenham	GB		51.90	-2.08	118836
Cheltenham	AU		-37.97	145.05	23992
Chelyabinsk	RU		55.16	61.43	1202371
Chemnitz	DE		50.84	12.93	247220
Chengalpattu	IN		12.69	79.98	65689
Chengde	CN		40.95	117.96	449325
Chengdu	CN		30.67	104.07	13568357
Chenggu	CN		33.15	107.33	116375
Chenghua	CN		23.46	116.77	152453
Chengqiao	CN		31.63	121.39	113442
Chengtangcun	CN		35.08	117.19	105456
Chengxian Chengguanzhen	CN		33.75	105.73	69427
Chengxiang	CN		31.40	109.57	89080
Chengyang	CN		35.58	118.83	66588
Chengzhong	CN		30.94	113.55	265886
Chengzihe	CN		45.34	131.00	98188
Chennai	IN		13.09	80.28	4681087
Chenzhou	CN		25.80	113.03	822534
Chenārān	IR		36.65	59.12	53879
Cheonan	KR		36.81	127.15	658831
Cheongju-si	KR		36.64	127.49	852147
Cheras	MY		3.11	101.73	135823
Cheremkhovo	RU		53.15	103.08	57395
Cheremushky	UA		46.43	30.71	120000
Cherepovets	RU		59.13	37.90	315738
Cheria	DZ		35.27	7.75	66160
Cherkasy	UA		49.44	32.06	269836
Cherkessk	RU		44.22	42.05	122395
Chernaya Rechka	RU		59.99	30.30	56429
Chernihiv	UA		51.51	31.29	282747
Chernivtsi	UA		48.29	25.93	264298
Chernogorsk	RU		53.83	91.31	71582
Cherry Hill	US	New Jersey	39.93	-75.03	70475
Cherry Hill	US	Virginia	38.57	-77.27	16000
Cherrybrook	AU		-33.72	151.05	18588
Chertanovo Yuzhnoye	RU		55.59	37.60	142000
Chertsey	GB		51.39	-0.51	15967
Cheruvannur	IN		11.19	75.83	61614
Cherëmushki	RU		55.66	37.56	106587
Chesapeake	US	Virginia	36.82	-76.27	235429
Chesham	GB		51.70	-0.60	20649
Cheshire	US	Connecticut	41.50	-72.90	29443
Cheshunt	GB		51.70	-0.03	43680
Chessington	GB		51.36	-0.30	19433
Chester	GB		53.19	-2.89	90524
Chester	US	Pennsylvania	39.85	-75.36	34092
Chester	US	Virginia	37.36	-77.44	20987
Chester-le-Street	GB		54.86	-1.57	36917
Chesterfield	GB		53.25	-1.42	113057
Chesterfield	US	Missouri	38.66	-90.58	47864
Chestermere	CA		51.03	-113.82	32255
Chestnut Hill	US	Massachusetts	42.33	-71.17	23649
Chetumal	MX		18.52	-88.30	169028
Cheyenne	US	Wyoming	41.14	-104.82	65132
Chełm	PL		51.14	23.47	60231
Chhatarpur	IN		24.92	79.59	142128
Chhibrāmau	IN		27.15	79.50	57071
Chhindwāra	IN		22.06	78.94	175052
Chiang Mai	TH		18.79	98.98	127240
Chiang Rai	TH		19.91	99.83	78756
Chiayi City	TW		23.48	120.45	263188
Chiba	JP		35.60	140.12	979768
Chibuto	MZ		-24.69	33.53	73393
Chicacao	GT		14.54	-91.33	60735
Chicago	US	Illinois	41.85	-87.65	2664452
Chicago Heights	US	Illinois	41.51	-87.64	30284
Chicago Lawn	US	Illinois	41.78	-87.70	55551
Chicago Loop	US	Illinois	41.88	-87.63	33442
Chichawatni	PK		30.53	72.69	112191
Chichester	GB		50.84	-0.78	31654
Chichibu	JP		35.99	139.08	61159
Chichicastenango	GT		14.94	-91.11	141567
Chickasha	US	Oklahoma	35.05	-97.94	16488
Chiclana de la Frontera	ES		36.42	-6.14	83831
Chiclayo	PE		-6.77	-79.85	609400
Chico	US	California	39.73	-121.84	121345
Chicoloapan	MX		19.42	-98.90	172919
Chicopee	US	Massachusetts	42.15	-72.61	56741
Chicoutimi	CA		48.42	-71.06	69004
Chidambaram	IN		11.40	79.69	62153
Chifeng	CN		42.27	118.96	346654
Chigasaki	JP		35.34	139.40	242798
Chigorodó	CO		7.67	-76.68	86239
Chiguayante	CL		-36.93	-73.03	84718
Chihuahua	MX		28.64	-106.09	925762
Chik Ballāpur	IN		13.44	77.73	63652
Chikhli	IN		20.35	76.26	57889
Chikmagalūr	IN		13.32	75.77	121484
Chikuma	JP		36.53	138.09	59381
Chikusei	JP		36.32	139.98	100753
Chikushino-shi	JP		33.50	130.52	103311
Chilakalūrupet	IN		16.09	80.17	101398
Chilanga Township	ZM		-15.57	28.27	54046
Chilanzar	UZ		41.28	69.18	260700
Chilca	PE		-12.09	-75.21	73371
Chililabombwe	ZM		-12.36	27.82	113876
Chilla Soroda Bāngar	IN		28.60	77.30	83217
Chillicothe	US	Ohio	39.33	-82.98	21727
Chilliwack	CA		49.17	-121.95	101491
Chilliwack-Downtown	CA		49.16	-121.96	31410
Chillum	US	Maryland	38.96	-76.99	33513
Chillán	CL		-36.61	-72.10	150396
Chilpancingo	MX		17.55	-99.50	187251
Chimaltenango	GT		14.66	-90.82	96985
Chimbas	AR		-31.49	-68.53	73829
Chimbote	PE		-9.08	-78.59	316966
Chimoio	MZ		-19.12	33.48	422046
Chinandega	NI		12.63	-87.13	126387
Chinatown	US	California	37.80	-122.41	100574
Chinatown	US	New York	40.72	-74.00	90000
Chinatown	CA		49.28	-123.11	24000
Chinautla	GT		14.70	-90.50	104972
Chinch'ŏn	KR		36.86	127.44	60964
Chincha Alta	PE		-13.41	-76.13	153076
Chinchiná	CO		4.98	-75.60	68512
Chingford	GB		51.63	0.00	70583
Chingola	ZM		-12.53	27.88	256560
Chinhoyi	ZW		-17.37	30.20	90800
Chiniot	PK		31.72	72.98	318165
Chinju	KR		35.19	128.08	307242
Chinnachowk	IN		14.48	78.84	64053
Chino	US	California	34.01	-117.69	85595
Chino	JP		35.99	138.15	56400
Chino Hills	US	California	33.99	-117.76	78309
Chintamani	IN		13.40	78.05	76068
Chinú	CO		9.11	-75.40	50743
Chipata	ZM		-13.63	32.65	327059
Chiplūn	IN		17.53	73.51	55139
Chippenham	GB		51.46	-2.12	35800
Chiquimula	GT		14.80	-89.55	111505
Chirchiq	UZ		41.47	69.58	162800
Chirmiri	IN		23.19	82.35	100800
Chiryū	JP		35.00	137.03	72193
Chishtian	PK		29.80	72.86	149939
Chisinau	MD		47.01	28.86	635994
Chislehurst	GB		51.42	0.07	15600
Chistopol’	RU		55.37	50.64	62200
Chiswick	GB		51.49	-0.26	34337
Chita	RU		52.04	113.49	349005
Chita	JP		35.00	136.86	84364
Chitato	AO		-7.30	20.73	246880
Chitose	JP		42.82	141.65	97950
Chitradurga	IN		14.22	76.40	145853
Chitral	PK		35.85	71.79	57157
Chittoor	IN		13.21	79.10	160722
Chittorgarh	IN		24.89	74.62	116406
Chitungwiza	ZW		-18.01	31.08	371246
Chivacoa	VE		10.16	-68.89	70298
Chivilcoy	AR		-34.90	-60.02	65575
Chiyoda	JP		35.68	139.75	66680
Chizhou	CN		30.66	117.48	615274
Chlef	DZ		36.17	1.33	178616
Choa Chu Kang New Town	SG		1.38	103.75	187550
Chodov	CZ		50.04	14.50	50043
Chokolivka	UA		50.42	30.45	73600
Chokwé	MZ		-24.53	32.98	63695
Cholet	FR		47.06	-0.88	53160
Choloma	HN		15.61	-87.95	139100
Cholula	MX		19.06	-98.30	292881
Chom Thong	TH		13.68	100.48	158005
Choma	ZM		-16.81	26.99	98974
Chomedey	CA		45.53	-73.75	94030
Chon Buri	TH		13.36	100.98	219164
Chongjin	KP		41.80	129.78	327000
Chonglong	CN		29.78	104.85	58441
Chongming	CN		31.62	121.70	637921
Chongqing	CN		29.56	106.56	7457599
Chongwe	ZM		-15.33	28.68	57443
Chongzuo	CN		22.38	107.37	384905
Chopda	IN		21.25	75.30	72783
Chorley	GB		53.65	-2.62	33888
Chornomors’k	UA		46.30	30.66	57983
Chortoq	UZ		41.07	71.82	53400
Chorzów	PL		50.31	18.97	113430
Choshi	JP		35.73	140.83	58431
Chosica	PE		-11.94	-76.71	88606
Choudwar	IN		20.54	85.92	52999
Chowchilla	US	California	37.12	-120.26	18510
Christchurch	NZ		-43.53	172.63	419200
Christchurch	GB		50.74	-1.78	31372
Christiansburg	US	Virginia	37.13	-80.41	21943
Christopher-Champlain	CA		43.35	-80.30	15372
Chuhar Kana	PK		31.75	73.80	69321
Chula Vista	US	California	32.64	-117.08	265757
Chulucanas	PE		-5.09	-80.16	68835
Chumakivskyi	UA		47.96	37.94	103005
Chumphon	TH		10.50	99.18	55835
Chuncheon	KR		37.87	127.73	284855
Chunga	ZM		-15.32	28.27	115539
Chungju	KR		36.98	127.93	209483
Chunian	PK		30.97	73.98	634236
Church-Yonge Corridor	CA		43.66	-79.38	31340
Chusovoy	RU		58.29	57.81	50205
Chust	UZ		41.00	71.24	100200
Chuxiong	CN		25.04	101.55	555081
Chuzhou	CN		32.32	118.30	782671
Chystyakove	UA		48.04	38.60	53462
Châlons-en-Champagne	FR		48.95	4.37	51257
Châteauguay	CA		45.38	-73.75	42786
Châteauroux	FR		46.81	1.69	53301
Châu Phong	VN		10.72	105.13	56322
Châu Đốc	VN		10.70	105.12	70239
Chéngguān Qū	CN		29.64	91.04	478275
Chí Linh	VN		21.07	106.32	220421
Chía	CO		4.86	-74.06	124309
Chóngfú	CN		30.53	120.43	112060
Chālūs	IR		36.66	51.42	107490
Chānda	IN		19.95	79.30	328351
Chāndpur	BD		23.23	90.65	203000
Chāndpur	IN		29.13	78.27	73555
Chāpra	IN		25.78	84.75	202352
Chāībāsa	IN		22.55	85.80	69565
Chīrāla	IN		15.82	80.35	92942
Chōfu	JP		35.66	139.55	242614
Chũ	VN		21.37	106.57	127881
Chūru	IN		28.30	74.97	120157
Chūō	JP		35.67	139.78	169179
Chơn Thành	VN		11.43	106.64	121083
Chợ Lớn	VN		10.75	106.65	561000
Ch’ŏngdan-ŭp	KP		37.97	125.94	142607
Ciamis	ID		-7.33	108.35	109839
Ciampea	ID		-6.55	106.70	207212
Cianjur	ID		-6.82	107.14	174587
Cianorte	BR		-23.66	-52.60	83816
Cibinong	ID		-6.48	106.85	363424
Cibolo	US	Texas	29.56	-98.23	33433
Cicero	US	Illinois	41.85	-87.75	83886
Cicero	US	New York	43.18	-76.12	31632
Cicurug	ID		-6.78	106.78	88965
Cidade Ademar	BR		-23.67	-46.66	249218
Cidade Dutra	BR		-23.73	-46.70	182459
Cidade Lider	BR		-23.56	-46.49	136660
Cidade Ocidental	BR		-16.11	-47.93	91767
Cidade Tiradentes	BR		-23.58	-46.40	192177
Ciego de Ávila	CU		21.84	-78.76	142027
Cienfuegos	CU		22.15	-80.45	186644
Cikampek	ID		-6.42	107.46	127173
Cikarang	ID		-6.26	107.15	106479
Cikupa	ID		-6.24	106.51	174041
Cilacap	ID		-7.73	109.01	256996
Cilegon	ID		-6.01	106.05	470378
Cileungsir	ID		-6.39	106.96	289833
Cileunyi	ID		-6.94	107.75	111476
Cimahi	ID		-6.87	107.54	581994
Cimarron Hills	US	Colorado	38.86	-104.70	16161
Cimitarra	CO		6.31	-73.95	50892
Cincinnati	US	Ohio	39.13	-84.51	311097
Cinco Ranch	US	Texas	29.74	-95.76	18274
Cinisello Balsamo	IT		45.56	9.21	75943
Cipolletti	AR		-38.93	-67.99	95524
Ciputat	ID		-6.24	106.70	207858
Ciranjang-hilir	ID		-6.82	107.26	77758
Circoiscrizione I	IT		45.07	7.69	78523
Circoiscrizione II	IT		45.05	7.64	141344
Circoiscrizione III	IT		45.06	7.63	130709
Circoiscrizione IV	IT		45.08	7.63	98787
Circoiscrizione V	IT		45.10	7.66	126666
Circoiscrizione VI	IT		45.10	7.70	107369
Circoiscrizione VII	IT		45.08	7.70	89448
Circoiscrizione VIII	IT		45.04	7.67	134028
Cirebon	ID		-6.71	108.56	344851
Cirencester	GB		51.72	-1.97	20229
Ciro	ET		7.83	38.23	69800
Citeureup	ID		-6.49	106.88	214668
Citrus Heights	US	California	38.71	-121.28	87056
Citrus Park	US	Florida	28.08	-82.57	24252
City of Isabela	PH		6.70	121.97	67336
City of Milford (balance)	US	Connecticut	41.22	-73.06	51271
City of Port Phillip	AU		-37.83	144.94	112669
City of Sammamish	US	Washington	47.60	-122.04	45780
City of Westminster	GB		51.50	-0.14	247614
Ciudad Acuña	MX		29.32	-100.95	216099
Ciudad Apodaca	MX		25.78	-100.19	467157
Ciudad Benito Juárez	MX		25.65	-100.09	308285
Ciudad Bolivia	VE		8.35	-70.57	52476
Ciudad Bolívar	VE		8.12	-63.55	412619
Ciudad Camilo Cienfuegos	CU		23.16	-82.33	178041
Ciudad Choluteca	HN		13.31	-87.18	75872
Ciudad de Huajuapan de León	MX		17.81	-97.78	53043
Ciudad de la Paz	GQ		1.59	10.82	2000
Ciudad de Villa de Álvarez	MX		19.27	-103.74	117600
Ciudad del Carmen	MX		18.65	-91.83	191238
Ciudad del Este	PY		-25.50	-54.65	301815
Ciudad Delicias	MX		28.19	-105.47	148045
Ciudad General Escobedo	MX		25.80	-100.32	454967
Ciudad Guayana	VE		8.35	-62.64	978202
Ciudad Guzmán	MX		19.70	-103.46	111975
Ciudad Hidalgo	MX		19.69	-100.56	60542
Ciudad Juárez	MX		31.72	-106.46	1512450
Ciudad Lineal	ES		40.45	-3.65	228171
Ciudad Lázaro Cárdenas	MX		17.96	-102.20	196003
Ciudad López Mateos	MX		19.56	-99.26	489160
Ciudad Madero	MX		22.25	-97.84	197216
Ciudad Mante	MX		22.74	-98.97	84787
Ciudad Nezahualcoyotl	MX		19.40	-99.01	1077208
Ciudad Obregón	MX		27.49	-109.94	329404
Ciudad Ojeda	VE		10.20	-71.31	240283
Ciudad Piar	VE		7.45	-63.32	51967
Ciudad Real	ES		38.99	-3.93	74743
Ciudad Río Bravo	MX		25.99	-98.09	95647
Ciudad Sandino	NI		12.16	-86.34	50000
Ciudad Satelite	PE		-16.43	-71.53	76410
Ciudad Valles	MX		22.00	-99.01	124644
Ciudad Victoria	MX		23.74	-99.14	332100
Ciutat Vella	ES		41.38	2.17	102347
Cixi	CN		30.18	121.25	1457510
Cizre	TR		37.33	42.18	134041
Ciénaga	CO		11.01	-74.25	88311
Clacton-on-Sea	GB		51.79	1.16	50548
Clairlea-Birchmount	CA		43.71	-79.28	26984
Clamart	FR		48.80	2.27	51400
Clanton Park	CA		43.74	-79.45	16472
Claremont	US	California	34.10	-117.72	36283
Claremore	US	Oklahoma	36.31	-95.62	18997
Clarence-Rockland	CA		45.55	-75.29	20790
Clark-Fulton	US	Ohio	41.46	-81.71	18185
Clarksburg	US	West Virginia	39.28	-80.34	16152
Clarksdale	US	Mississippi	34.20	-90.57	16847
Clarksville	US	Tennessee	36.53	-87.36	166722
Clarksville	US	Indiana	38.30	-85.76	21866
Clay	US	New York	43.19	-76.17	58206
Clayton	US	North Carolina	35.65	-78.46	19304
Clayton	AU		-37.92	145.12	18988
Clayton	US	Missouri	38.64	-90.32	15884
Clayton Park West	CA		44.66	-63.67	16550
Clearfield	US	Utah	41.11	-112.03	30653
Clearlake	US	California	38.96	-122.63	15182
Clearwater	US	Florida	27.97	-82.80	117292
Cleburne	US	Texas	32.35	-97.39	30020
Cleckheaton	GB		53.72	-1.71	27393
Cleethorpes	GB		53.56	-0.03	38996
Clementi Housing Estate	SG		1.32	103.76	92420
Clemmons	US	North Carolina	36.02	-80.38	19844
Clemson	US	South Carolina	34.68	-82.84	15446
Clermont	US	Florida	28.55	-81.77	32390
Clermont-Ferrand	FR		45.78	3.09	147865
Clevedon	GB		51.44	-2.86	21002
Cleveland	US	Ohio	41.50	-81.70	365379
Cleveland	US	Tennessee	35.16	-84.88	43898
Cleveland Heights	US	Ohio	41.52	-81.56	44962
Clichy	FR		48.90	2.31	57467
Cliffcrest	CA		43.72	-79.23	15935
Cliffside Park	US	New Jersey	40.82	-73.99	24857
Clifton	US	New Jersey	40.86	-74.16	86334
Clifton	US	Colorado	39.09	-108.45	19889
Clifton Park	US	New York	42.87	-73.77	36705
Clinton	US	Maryland	38.77	-76.90	35970
Clinton	US	Iowa	41.84	-90.19	26064
Clinton	US	Mississippi	32.34	-90.32	25254
Clinton	US	Utah	41.14	-112.05	21399
Clinton Township	US	Michigan	42.59	-82.92	99753
Clive	US	Iowa	41.60	-93.72	15447
Closepet	IN		12.72	77.28	95167
Cloverdale	CA		49.11	-122.73	73355
Cloverleaf	US	Texas	29.78	-95.17	22942
Cloverly	US	Maryland	39.11	-77.00	15126
Clovis	US	California	36.83	-119.70	104180
Clovis	US	New Mexico	34.40	-103.21	39480
Cluain Meala	IE		52.35	-7.70	18369
Cluj-Napoca	RO		46.77	23.60	286598
Clydach	GB		51.68	-3.90	19307
Clydebank	GB		55.90	-4.41	25620
Coacalco	MX		19.63	-99.11	277959
Coachella	US	California	33.68	-116.17	44635
Coalinga	US	California	36.14	-120.36	16564
Coalville	GB		52.72	-1.37	37661
Coari	BR		-4.08	-63.14	73820
Coatbridge	GB		55.86	-4.02	43950
Coatepec	MX		19.45	-96.96	53621
Coatepeque	GT		14.70	-91.86	105415
Coatzacoalcos	MX		18.15	-94.44	310698
Cobbs Creek	US	Pennsylvania	39.95	-75.24	33373
Cobham	GB		51.33	-0.41	16724
Cobourg	CA		43.96	-78.17	18099
Coburg	AU		-37.75	144.97	26574
Cobán	GT		15.47	-90.37	212047
Cochabamba	BO		-17.38	-66.16	841276
Cochrane	CA		51.18	-114.47	32199
Cockburn Town	TC		21.46	-71.14	3720
Cockeysville	US	Maryland	39.48	-76.64	20776
Cocoa	US	Florida	28.39	-80.74	17711
Coconut Creek	US	Florida	26.25	-80.18	59302
Coconut Grove	US	Florida	25.71	-80.26	20076
Cocorote	VE		10.32	-68.78	52803
Codó	BR		-4.46	-43.89	114275
Coeur d'Alene	US	Idaho	47.68	-116.78	49122
Coffs Harbour	AU		-30.30	153.11	78759
Cogan	PH		10.59	124.02	60230
Cohoes	US	New York	42.77	-73.70	16538
Coimbatore	IN		11.01	76.97	2136916
Coimbra	PT		40.21	-8.42	140796
Coity	GB		51.52	-3.56	41352
Colatina	BR		-19.54	-40.63	101190
Colcapirhua	BO		-17.39	-66.24	52732
Colchester	GB		51.89	0.90	130245
Colchester	US	Vermont	44.54	-73.15	16986
Cole Harbour	CA		44.67	-63.48	19096
Colegiales	AR		-34.57	-58.45	57000
Coleraine	GB		55.13	-6.67	25681
Colima	MX		19.24	-103.71	146965
Colina	CL		-33.20	-70.67	146207
Collado-Villalba	ES		40.64	-4.00	63074
College Park	US	Maryland	38.98	-76.94	32301
College Point	US	New York	40.79	-73.85	27307
College Station	US	Texas	30.63	-96.33	107889
Colleyville	US	Texas	32.88	-97.16	25487
Collierville	US	Tennessee	35.04	-89.66	48863
Collingwood	CA		44.48	-80.22	21793
Collinsville	US	Illinois	38.67	-89.98	24754
Collinwood	US	Ohio	41.56	-81.57	34220
Colmar	FR		48.08	7.36	65405
Colne	GB		53.86	-2.17	20118
Colombes	FR		48.92	2.25	82300
Colombo	LK		6.94	79.85	648034
Colombo	BR		-25.29	-49.22	232212
Colonia	US	New Jersey	40.57	-74.30	17795
Colonia del Valle	MX		19.39	-99.16	250000
Colonia Lindavista	MX		19.49	-99.12	100000
Colonia Nativitas	MX		19.38	-99.14	60000
Colonial Heights	US	Virginia	37.27	-77.41	17820
Colorado Springs	US	Colorado	38.83	-104.82	456568
Colton	US	California	34.07	-117.31	54621
Columbia	US	South Carolina	34.00	-81.03	142416
Columbia	US	Missouri	38.95	-92.33	129330
Columbia	US	Maryland	39.24	-76.84	99615
Columbia	US	Tennessee	35.62	-87.04	36800
Columbia City	US	Washington	47.56	-122.28	19000
Columbia Heights	US	District of Columbia	38.93	-77.03	38000
Columbia Heights	US	Minnesota	45.04	-93.26	19715
Columbine	US	Colorado	39.59	-105.07	24280
Columbus	US	Ohio	39.96	-83.00	913175
Columbus	US	Georgia	32.46	-84.99	206922
Columbus	US	Indiana	39.20	-85.92	46690
Columbus	US	Mississippi	33.50	-88.43	23168
Columbus	US	Nebraska	41.43	-97.37	22797
Colwood	CA		48.43	-123.49	16859
Colwyn Bay	GB		53.29	-3.73	29275
Colón	PA		9.36	-79.90	78000
Colón	CU		22.72	-80.90	63882
Colón	VE		8.03	-72.26	62513
Colón	AR		-32.22	-58.14	58219
Comal	ID		-6.91	109.53	51092
Comayagua	HN		14.46	-87.64	58784
Comilla	BD		23.46	91.19	634654
Comitancillo	GT		15.09	-91.75	59489
Comitán	MX		16.24	-92.14	166178
Commack	US	New York	40.84	-73.29	36124
Commerce City	US	Colorado	39.81	-104.93	53696
Commonwealth	PH		14.70	121.08	215034
Como	IT		45.81	9.08	84808
Comodoro Rivadavia	AR		-45.86	-67.49	140850
Compton	US	California	33.90	-118.22	98462
Conakry	GN		9.54	-13.68	1928389
Conceição do Coité	BR		-11.56	-39.28	67825
Concepcion	PH		15.33	120.66	178549
Concepción	CL		-36.83	-73.05	223574
Concepción	VE		10.41	-71.69	92463
Concepción del Uruguay	AR		-32.48	-58.23	67895
Conception Bay South	CA		47.50	-53.00	27168
Concord	US	California	37.98	-122.03	128667
Concord	US	North Carolina	35.41	-80.58	87696
Concord	US	New Hampshire	43.21	-71.54	43976
Concord	US	Massachusetts	42.46	-71.35	16810
Concord	US	Missouri	38.52	-90.36	16421
Concordia	AR		-31.39	-58.02	145210
Concórdia	BR		-27.23	-52.03	81646
Conda	US	Idaho	42.73	-111.53	21260
Coney Island	US	New York	40.58	-73.99	60000
Confederation	CA		52.14	-106.70	70192
Congleton	GB		53.16	-2.21	26178
Congonhas	BR		-20.51	-43.86	52890
Conisbrough	GB		53.48	-1.23	15934
Conroe	US	Texas	30.31	-95.46	68602
Conselheiro Lafaiete	BR		-20.66	-43.79	111596
Consett	GB		54.85	-1.83	29137
Consolación del Sur	CU		22.51	-83.51	69857
Consolação	BR		-23.55	-46.66	53249
Constantine	DZ		36.37	6.61	448028
Constanţa	RO		44.18	28.63	317832
Contagem	BR		-19.93	-44.05	627123
Contai	IN		21.78	87.75	88702
Contramaestre	CU		20.30	-76.24	70438
Converse	US	Texas	29.52	-98.32	21987
Conway	US	Arkansas	35.09	-92.44	64980
Conway	US	South Carolina	33.84	-79.05	21053
Conyers	US	Georgia	33.67	-84.02	15875
Coogee	AU		-33.92	151.26	15333
Cookeville	US	Tennessee	36.16	-85.50	32113
Coon Rapids	US	Minnesota	45.12	-93.29	62240
Cooper City	US	Florida	26.06	-80.27	35364
Coorparoo	AU		-27.49	153.06	15965
Coos Bay	US	Oregon	43.37	-124.22	16182
Copacabana	BR		-22.97	-43.19	128919
Copenhagen	DK		55.68	12.57	1153615
Copiague	US	New York	40.68	-73.40	22993
Copiapó	CL		-27.37	-70.33	129280
Coppell	US	Texas	32.95	-97.02	41159
Copperas Cove	US	Texas	31.12	-97.90	33081
Coquimbo	CL		-29.95	-71.34	161317
Coquitlam	CA		49.28	-122.78	148625
Coquitlam Town Centre	CA		49.28	-122.80	24282
Coquitlam West	CA		49.26	-122.88	25656
Coral Gables	US	Florida	25.72	-80.27	51117
Coral Springs	US	Florida	26.27	-80.27	129485
Coral Terrace	US	Florida	25.75	-80.30	24376
Coralville	US	Iowa	41.68	-91.58	20608
Coram	US	New York	40.87	-73.00	39113
Corby	GB		52.50	-0.69	68164
Corcoran	US	California	36.10	-119.56	22477
Cordova	US	Tennessee	35.16	-89.78	68779
Core Neighbourhoods	CA		52.13	-106.67	36088
Corinth	US	Texas	33.15	-97.06	20998
Corio	AU		-38.08	144.38	15215
Cork	IE		51.90	-8.47	224004
Cornelius	US	North Carolina	35.49	-80.86	28092
Cornellà de Llobregat	ES		41.35	2.08	87173
Corner Brook	CA		48.95	-57.95	19316
Cornwall	CA		45.02	-74.73	48821
Coro	VE		11.41	-69.68	246657
Coroatá	BR		-4.13	-44.12	61351
Corona	US	California	33.88	-117.57	164226
Corona	US	New York	40.75	-73.86	109698
Coronado	US	California	32.69	-117.18	24812
Coronel	CL		-37.03	-73.14	107759
Coronel Fabriciano	BR		-19.52	-42.63	104736
Coronel Oviedo	PY		-25.45	-56.44	51286
Corpus Christi	US	Texas	27.80	-97.40	316239
Corralillo	CU		22.98	-80.59	51881
Corrientes	AR		-27.47	-58.83	346334
Corroios	PT		38.64	-9.15	52520
Corsicana	US	Texas	32.10	-96.47	23952
Cortazar	MX		20.48	-100.96	61658
Cortland	US	New York	42.60	-76.18	18907
Cortlandt Manor	US	New York	41.28	-73.87	19929
Corumbá	BR		-19.01	-57.65	96520
Coruripe	BR		-10.13	-36.18	51788
Corvallis	US	Oregon	44.56	-123.26	55780
Cosenza	IT		39.30	16.25	63852
Coslada	ES		40.42	-3.56	81860
Cosmópolis	BR		-22.65	-47.20	59773
Costa Mesa	US	California	33.64	-117.92	113204
Cotabato	PH		7.22	124.25	383383
Cotia	BR		-23.60	-46.92	253608
Cotonou	BJ		6.37	2.42	679012
Cottage Grove	US	Minnesota	44.83	-92.94	35918
Cottage Lake	US	Washington	47.74	-122.08	22494
Cottbus	DE		51.76	14.33	84754
Cottonwood Heights	US	Utah	40.62	-111.81	34343
Coulsdon	GB		51.32	-0.14	25530
Council Bluffs	US	Iowa	41.26	-95.86	62597
Country Club	US	Florida	25.95	-80.32	47105
Country Club Hills	US	Illinois	41.57	-87.72	16795
Country Walk	US	Florida	25.63	-80.43	15997
Courbevoie	FR		48.90	2.26	85158
Courtenay	CA		49.69	-124.99	28420
Coventry	GB		52.41	-1.51	345324
Coventry	US	Rhode Island	41.70	-71.68	35525
Coventry Hills	CA		51.17	-114.06	17350
Covina	US	California	34.09	-117.89	48984
Covington	US	Kentucky	39.08	-84.51	40997
Covington	US	Washington	47.36	-122.12	19197
Cowes	GB		50.76	-1.30	21226
Cowley	GB		51.73	-1.21	16500
Cox’s Bāzār	BD		21.44	92.01	253788
Coyah	GN		9.71	-13.38	77103
Coyoacán	MX		19.35	-99.16	614447
Cozumel	MX		20.50	-86.94	77236
Craigavon	GB		54.45	-6.39	59236
Craigieburn	AU		-37.60	144.95	65178
Craiova	RO		44.32	23.80	234140
Cramlington	GB		55.09	-1.59	33180
Cranberry Township	US	Pennsylvania	40.68	-80.11	28098
Cranbourne	AU		-38.11	145.28	21281
Cranbourne East	AU		-38.12	145.30	24679
Cranbourne North	AU		-38.08	145.30	24683
Cranbourne West	AU		-38.10	145.27	19969
Cranbrook	CA		49.50	-115.77	20047
Cranebrook	AU		-33.71	150.71	15649
Cranford	US	New Jersey	40.66	-74.30	22627
Cranston	US	Rhode Island	41.78	-71.44	81073
Cranston	CA		50.89	-113.98	20850
Crateús	BR		-5.18	-40.67	76390
Crato	BR		-7.23	-39.41	131050
Crawfordsville	US	Indiana	40.04	-86.87	16024
Crawley	GB		51.11	-0.18	124008
Cremona	IT		45.13	10.02	71223
Crest Hill	US	Illinois	41.55	-88.10	21153
Crestview	US	Florida	30.76	-86.57	23270
Creve Coeur	US	Missouri	38.66	-90.42	18276
Crewe	GB		53.10	-2.44	76437
Criciúma	BR		-28.68	-49.37	161954
Cricklewood	GB		51.56	-0.22	65000
Cristalina	BR		-16.77	-47.62	60210
Cristo Rey	DO		18.50	-69.93	57084
Crofton	US	Maryland	39.00	-76.69	27348
Croix-des-Bouquets	HT		18.58	-72.23	229127
Cronulla	AU		-34.06	151.15	17703
Crotone	IT		39.08	17.13	64603
Crowborough	GB		51.06	0.16	21688
Crown Point	US	Indiana	41.42	-87.37	28879
Crowthorne	GB		51.37	-0.79	25522
Croydon	GB		51.38	-0.10	173314
Croydon	AU		-37.80	145.28	26502
Cruz Alta	BR		-28.64	-53.61	58913
Cruz das Almas	BR		-12.67	-39.10	60348
Cruzeiro	BR		-22.57	-44.97	74961
Cruzeiro do Sul	BR		-7.63	-72.68	91888
Crystal	US	Minnesota	45.03	-93.36	22943
Crystal Lake	US	Illinois	42.24	-88.32	40448
Créteil	FR		48.79	2.47	84833
Cuamba	MZ		-14.80	36.54	91780
Cuango-Luzamba	AO		-9.15	18.04	55000
Cuauhtémoc	MX		19.45	-99.15	531831
Cuauhtémoc	MX		28.41	-106.87	168482
Cuautitlán	MX		19.67	-99.18	178847
Cuautitlán Izcalli	MX		19.64	-99.22	555163
Cuautla	MX		18.81	-98.94	157336
Cubal	AO		-13.04	14.25	90367
Cubatão	BR		-23.89	-46.43	112476
Cudahy	US	California	33.96	-118.19	24311
Cudahy	US	Wisconsin	42.96	-87.86	18353
Cuddalore	IN		11.76	79.77	173636
Cuenca	EC		-2.90	-79.00	636996
Cuenca	ES		40.07	-2.13	54898
Cuernavaca	MX		18.93	-99.23	338650
Cuiabá	BR		-15.60	-56.10	618124
Cukai	MY		4.25	103.42	82425
Culiacán	MX		24.80	-107.39	808416
Cullman	US	Alabama	34.17	-86.84	15350
Culpeper	US	Virginia	38.47	-78.00	17557
Culver City	US	California	34.02	-118.40	39717
Cumaná	VE		10.46	-64.18	405626
Cumberland	US	Rhode Island	41.97	-71.43	34843
Cumberland	US	Maryland	39.65	-78.76	20130
Cumbernauld	GB		55.95	-3.99	50530
Cumbum	IN		9.74	77.28	68090
Cuneo	IT		44.39	7.55	55980
Cung Kiệm	VN		21.19	106.16	80000
Cupang	PH		14.43	121.04	57482
Cupertino	US	California	37.32	-122.03	60572
Curepipe	MU		-20.32	57.53	78618
Curicó	CL		-34.98	-71.24	102438
Curitiba	BR		-25.43	-49.27	1948626
Cursino	BR		-23.63	-46.62	103171
Curug	ID		-6.27	106.56	191406
Curvelo	BR		-18.76	-44.43	80665
Cusco	PE		-13.53	-71.97	428450
Cutler	US	Florida	25.62	-80.31	18117
Cutler Bay	US	Florida	25.58	-80.34	45425
Cutler Ridge	US	Florida	25.58	-80.35	26831
Cuttack	IN		20.46	85.88	610189
Cuxhaven	DE		53.87	8.70	52677
Cuyahoga Falls	US	Ohio	41.13	-81.48	49146
Cuíto	AO		-12.38	16.93	355423
Cwmbran	GB		51.65	-3.02	48535
Cyberjaya	MY		2.92	101.66	79200
Cypress	US	Texas	29.97	-95.70	200839
Cypress	US	California	33.82	-118.04	49290
Cypress Hills	US	New York	40.68	-73.89	54944
Częstochowa	PL		50.80	19.12	248125
Cà Mau	VN		9.18	105.15	226372
Cáceres	ES		39.48	-6.37	96068
Cáceres	BR		-16.07	-57.68	91626
Cái Răng	VN		10.00	105.75	86278
Cárdenas	CU		23.04	-81.21	98515
Cárdenas	MX		18.00	-93.38	91558
Córdoba	AR		-31.41	-64.19	2106734
Córdoba	ES		37.89	-4.77	325708
Córdoba	MX		18.88	-96.93	204721
Côte-Saint-Luc	CA		45.47	-73.67	31395
Cúa	VE		10.16	-66.88	182558
Cúcuta	CO		7.91	-72.50	777106
Cần Giuộc	VN		10.61	106.67	152200
Cần Giờ	VN		10.41	106.95	55137
Cần Thơ	VN		10.04	105.79	1507187
Cần Đước	VN		10.51	106.60	50473
Cầu Giấy	VN		21.03	105.80	292536
Cẩm Lệ	VN		16.02	108.20	78837
Cẩm Phả	VN		21.01	107.27	190232
Cẩm Phả Mines	VN		21.02	107.30	135477
Cổ Đô	VN		21.28	105.36	70706
Cờ Đỏ	VN		10.09	105.43	116576
Củ Chi	VN		10.97	106.49	75000
Cửa Nam	VN		21.02	105.85	52750
Da Nang	VN		16.07	108.22	1276000
Daanbantayan	PH		11.25	124.01	95080
Dabhel	IN		20.41	72.88	52578
Dabhoi	IN		22.18	73.43	56253
Dabou	CI		5.33	-4.38	138083
Dabra	IN		25.89	78.33	61277
Dabwāli	IN		29.95	74.74	62113
Dachang	CN		31.31	121.42	371856
Dacheng	CN		19.51	109.39	84620
Dachnoye	RU		59.84	30.26	72822
Dadu	PK		26.73	67.78	201017
Daegu	KR		35.87	128.59	2365523
Daejeon	KR		36.35	127.38	1441203
Daet	PH		14.11	122.96	78142
Dagenham	GB		51.55	0.17	108368
Dagupan	PH		16.04	120.33	171271
Daharki	PK		28.05	69.70	90177
Dainava (Kaunas)	LT		54.92	23.97	70000
Daisen	JP		39.44	140.49	91143
Daitō	JP		34.71	135.62	119367
Dajal	PK		29.56	70.38	200000
Dakar	SN		14.69	-17.44	2646503
Dakhla	EH		23.68	-15.96	106277
Dakhla	MA		30.41	-9.55	55618
Dakota Ridge	US	Colorado	39.62	-105.14	33892
Dalai	CN		45.50	124.30	93297
Dale City	US	Virginia	38.64	-77.31	65969
Dali	CN		25.58	100.21	235305
Dali Old Town	CN		25.69	100.16	82566
Dalian	CN		38.91	121.60	4913879
Daliang	CN		22.84	113.25	210411
Dalianwan	CN		39.03	121.69	55841
Dallas	US	Texas	32.78	-96.81	1326087
Dallas	US	Oregon	44.92	-123.32	15277
Daloa	CI		6.88	-6.45	421871
Dalserf	GB		55.73	-3.92	17985
Dalton	US	Georgia	34.77	-84.97	33853
Daly City	US	California	37.71	-122.46	106562
Dalūpura	IN		28.61	77.32	154791
Dam Dam	IN		22.63	88.42	122719
Damanhur	EG		31.03	30.47	318207
Damansara Damai	MY		3.20	101.59	85000
Damascus	SY		33.51	36.29	1569394
Damascus	US	Maryland	39.29	-77.20	15257
Dambulla	LK		7.86	80.65	66716
Damiao	CN		34.26	117.36	77179
Damietta	EG		31.42	31.81	305920
Dammam	SA		26.43	50.10	1252523
Damoh	IN		23.83	79.44	139561
Dana Point	US	California	33.47	-117.70	34181
Danané	CI		7.26	-8.15	78614
Danao	PH		10.52	124.03	70270
Danbury	US	Connecticut	41.39	-73.45	84657
Dandeli	IN		15.27	74.62	52295
Dandenong	AU		-37.98	145.20	30127
Dandenong North	AU		-37.97	145.21	22550
Dandong	CN		40.13	124.39	631973
Danforth East York	CA		43.69	-79.33	17180
Dangila	ET		11.27	36.83	56000
Dangkao	KH		11.51	104.89	76421
Dania Beach	US	Florida	26.05	-80.14	31446
Danjiangkou	CN		32.54	111.51	92008
Danlí	HN		14.03	-86.58	233789
Danshui	TW		25.17	121.44	189271
Danshui	CN		22.80	114.47	126701
Danvers	US	Massachusetts	42.58	-70.93	26493
Danville	US	California	37.82	-122.00	44400
Danville	US	Virginia	36.59	-79.40	42082
Danville	US	Illinois	40.12	-87.63	32108
Danville	US	Kentucky	37.65	-84.77	16690
Daokou	CN		35.57	114.52	56637
Daotian	CN		36.83	118.90	93728
Daoukro	CI		7.06	-3.96	101136
Dapaong	TG		10.86	0.21	58071
Dapeng	CN		34.28	117.08	52219
Daphne	US	Alabama	30.60	-87.90	24896
Dapitan	PH		8.66	123.42	87699
Daqing	CN		46.58	125.00	1604027
Dar Bouazza	MA		33.52	-7.82	165295
Dar es Salaam	TZ		-6.82	39.27	5383728
Dar Naim	MR		18.11	-15.93	61089
Darbhanga	IN		26.15	85.90	296039
Darhan	MN		49.49	105.92	83883
Darien	US	Illinois	41.75	-87.97	22256
Darien	US	Connecticut	41.08	-73.47	20732
Darlington	GB		54.52	-1.55	92363
Darmstadt	DE		49.87	8.65	167029
Darnah	LY		32.77	22.64	102581
Darnytskyi Masyv	UA		50.44	30.63	68900
Darnytsya	UA		50.42	30.70	343384
Dartford	GB		51.45	0.21	51240
Dartmouth	CA		44.67	-63.58	101343
Darton	GB		53.59	-1.53	21345
Darwen	GB		53.70	-2.46	32566
Darwin	AU		-12.46	130.84	139902
Darya Khan	PK		31.78	71.10	68622
Darāw	EG		24.41	32.92	61790
Dar‘ā	SY		32.62	36.10	97969
Dasha	CN		23.11	113.44	116307
Dashahe	CN		34.54	116.62	51916
Dashi	CN		30.09	106.22	61426
Dashiqiao	CN		40.64	122.50	80223
Dashitou	CN		43.31	128.51	65683
Daska Kalan	PK		32.32	74.35	126924
Dasmariñas	PH		14.33	120.94	441876
Date	JP		37.82	140.50	59625
Datia	IN		25.67	78.46	100284
Datong	CN		40.09	113.29	1850000
Datong	CN		32.62	117.06	61085
Datong	CN		28.60	106.67	51025
Datun	CN		34.81	116.90	110258
Daudnagar	IN		25.03	84.40	52364
Daugavpils	LV		55.88	26.53	78126
Daule	EC		-1.86	-79.98	173684
Daur	PK		26.46	68.32	128958
Daura	NG		11.55	11.41	78277
Dausa	IN		26.89	76.34	85960
Davangere	IN		14.47	75.93	435128
Davao	PH		7.07	125.61	1848947
Davenport	US	Iowa	41.52	-90.58	102582
Daventry	GB		52.26	-1.16	28123
David	PA		8.43	-82.43	82907
Davie	US	Florida	26.06	-80.23	100882
Davis	US	California	38.54	-121.74	67666
Davtashen	AM		40.22	44.48	52100
Dawbon	MM		16.52	95.60	75325
Dawei	MM		14.08	98.19	136783
Dawukou	CN		39.04	106.40	131880
Daxi	TW		24.88	121.29	94222
Daxing	CN		39.74	116.33	104904
Daxing	CN		27.26	100.86	52568
Daxing’anling	CN		52.33	124.71	520000
Daxu	CN		34.28	117.55	66563
Daye	CN		30.08	114.95	347406
Dayr al Balaḩ	PS		31.42	34.35	59504
Dayr Mawās	EG		27.64	30.85	60835
Dayrah	AE		25.27	55.30	400000
Dayrūţ	EG		27.56	30.81	102570
Dayton	US	Ohio	39.76	-84.19	135512
Daytona Beach	US	Florida	29.21	-81.02	72647
Dazaifu	JP		33.51	130.52	73164
Dazeshan	CN		36.99	119.92	60034
Dazhong	CN		33.20	120.46	84323
Dazhou	CN		31.21	107.46	1589435
Daşoguz	TM		41.84	59.97	201142
Dchira El Jihadia	MA		30.37	-9.55	109564
De Pere	US	Wisconsin	44.45	-88.06	24724
Deal	GB		51.22	1.40	30917
Dearborn	US	Michigan	42.32	-83.18	95171
Dearborn Heights	US	Michigan	42.34	-83.27	56145
DeBary	US	Florida	28.88	-81.31	19998
Debre Birhan	ET		9.68	39.53	146900
Debre Mark’os	ET		10.35	37.73	140700
Debre Tabor	ET		11.85	38.02	125300
Debrecen	HU		47.53	21.62	202402
Decatur	US	Illinois	39.84	-88.95	73254
Decatur	US	Alabama	34.61	-86.98	55437
Decatur	US	Georgia	33.77	-84.30	21957
Deception Bay	AU		-27.19	153.03	19539
Dedham	US	Massachusetts	42.24	-71.17	24729
Dee Why	AU		-33.75	151.29	21145
Deer Park	US	Texas	29.71	-95.12	33806
Deer Park	US	New York	40.76	-73.33	27745
Deer Park	AU		-37.77	144.77	18145
Deer Valley	US	Arizona	33.68	-112.13	165656
Deerfield	US	Illinois	42.17	-87.84	19019
Deerfield Beach	US	Florida	26.32	-80.10	79768
Deesa	IN		24.26	72.18	111160
Deeside	GB		53.20	-3.04	32000
Defiance	US	Ohio	41.28	-84.36	16776
Degan	CN		29.28	106.23	83950
Deglur	IN		18.55	77.58	54493
Dehdasht	IR		30.79	50.57	57036
Dehiwala-Mount Lavinia	LK		6.84	79.87	219827
Dehradun	IN		30.32	78.03	522081
Dehui	CN		44.54	125.69	108818
Deir ez-Zor	SY		35.34	40.14	271800
DeKalb	US	Illinois	41.93	-88.75	43211
Del City	US	Oklahoma	35.44	-97.44	22022
Del Rio	US	Texas	29.36	-100.90	36153
DeLand	US	Florida	29.03	-81.30	30195
Delano	US	California	35.77	-119.25	52733
Delaware	US	Ohio	40.30	-83.07	37995
Delegación Cuajimalpa de Morelos	MX		19.37	-99.29	160491
Delft	NL		52.01	4.36	95060
Delgado	SV		13.72	-89.17	71594
Delhi	IN		28.65	77.23	11034555
Delhi Cantonment	IN		28.60	77.13	110351
Delicias	ES		41.65	-0.91	110520
Delmas	HT		18.54	-72.30	395260
Delmas	ZA		-26.15	28.68	92046
Delmenhorst	DE		53.05	8.63	75893
Delmiro Gouveia	BR		-9.39	-38.00	52809
Delray Beach	US	Florida	26.46	-80.07	66255
Delta	CA		49.09	-123.05	101668
Deltona	US	Florida	28.90	-81.26	88474
Dembī Dolo	ET		8.53	34.80	61100
Den Helder	NL		52.96	4.76	59569
Dengbu	CN		28.21	116.82	63814
Dengzhou	CN		32.68	112.09	285032
Dengzhou	CN		37.81	120.76	85279
Denison	US	Texas	33.76	-96.54	23150
Denizli	TR		37.77	29.09	313238
Denov	UZ		38.27	67.90	78300
Denpasar	ID		-8.65	115.22	670210
Denton	US	Texas	33.21	-97.13	131044
Denton	GB		53.46	-2.12	27464
Denver	US	Colorado	39.74	-104.98	729019
Denville	US	New Jersey	40.89	-74.48	16669
Deoband	IN		29.70	77.68	88171
Deoghar	IN		24.49	86.70	203123
Deoli	IN		28.50	77.23	169122
Deolāli	IN		19.94	73.83	54027
Deoria	IN		26.50	83.78	129570
Depew	US	New York	42.90	-78.69	15146
Depok	ID		-6.40	106.82	2163635
Depok	ID		-7.76	110.43	104527
Deqing	CN		30.54	119.96	87576
Dera Ghazi Khan	PK		30.05	70.64	494464
Dera Ismail Khan	PK		31.83	70.90	763195
Dera Murad Jamali	PK		28.55	68.22	106952
Derbent	RU		42.07	48.29	105965
Derby	GB		52.92	-1.48	270468
Derby	US	Kansas	37.55	-97.27	23509
Derince	TR		40.76	29.81	125485
Derry	GB		55.00	-7.31	83652
Derry	US	New Hampshire	42.88	-71.33	22015
Derry Village	US	New Hampshire	42.89	-71.31	34539
Des Moines	US	Iowa	41.60	-93.61	214133
Des Moines	US	Washington	47.40	-122.32	31221
Des Plaines	US	Illinois	42.03	-87.88	58677
Desert Hot Springs	US	California	33.96	-116.50	28335
Desmarchais-Crawford	CA		45.45	-73.58	29688
Desna	UA		50.52	30.68	368500
Desnyanskyi	UA		51.51	31.32	179600
DeSoto	US	Texas	32.59	-96.86	52486
Dessalines	HT		19.26	-72.52	181903
Dessau	DE		51.84	12.25	67747
Dessie	ET		11.13	39.63	270400
Detmold	DE		51.94	8.87	73680
Detroit	US	Michigan	42.33	-83.05	645705
Detroit-Shoreway	US	Ohio	41.48	-81.73	17382
Deurne	BE		51.22	4.47	78747
Deux-Montagnes	CA		45.53	-73.90	17402
Deva	RO		45.88	22.90	67802
Devakottai	IN		9.95	78.82	51865
Deventer	NL		52.26	6.16	97331
Devizes	GB		51.35	-1.99	16834
Devonport	AU		-41.18	146.35	26150
Dewas	IN		22.97	76.06	289550
Dewdney East	CA		50.45	-104.55	18715
Dewsbury	GB		53.69	-1.63	61035
Deyang	CN		31.13	104.38	735070
Dezful	IR		32.38	48.41	264709
Dezhou	CN		37.45	116.37	679535
Deçan	XK		42.54	20.29	50500
Dhahran	SA		26.29	50.11	99540
Dhaka	BD		23.71	90.41	10356500
Dhamtari	IN		20.71	81.55	101677
Dhamār	YE		14.54	44.41	160114
Dhanbad	IN		23.80	86.43	1196214
Dhangaḍhi̇̄	NP		28.70	80.59	204788
Dhanmondi	BD		23.74	90.39	54210
Dharapuram	IN		10.74	77.53	72291
Dharashiv	IN		18.18	76.04	112085
Dharmapuri	IN		12.13	78.16	68619
Dharmavaram	IN		14.41	77.72	121874
Dharān	NP		26.81	87.28	173096
Dhaulpur	IN		26.69	77.88	133075
Dhenkānāl	IN		20.66	85.60	67414
Dhirkot	PK		34.04	73.58	195000
Dholka	IN		22.73	72.44	80945
Dhone	IN		15.40	77.87	59272
Dhoraji	IN		21.73	70.45	84545
Dhrāngadhra	IN		22.99	71.47	75578
Dhubri	IN		26.02	89.99	63388
Dhule	IN		20.90	74.78	375559
Dhuliān	IN		24.68	87.95	77070
Dhār	IN		22.59	75.30	93917
Dhārāvi	IN		19.05	72.87	700000
Dhūri	IN		30.37	75.87	55225
Diadema	BR		-23.69	-46.62	393237
Dialakorodji	ML		12.70	-7.96	70619
Diamond Bar	US	California	34.03	-117.81	56897
Diamond Head / Kapahulu / Saint Louis Heights	US	Hawaii	21.28	-157.81	19769
Dianbu	CN		36.70	120.35	52613
Dianella	AU		-31.89	115.87	24169
Dianzi	CN		36.90	119.87	51267
Dias d'Ávila	BR		-12.61	-38.30	71485
Dibaya-Lubwe	CD		-4.16	19.86	55672
Dibrugarh	IN		27.48	94.91	145488
Dickinson	US	North Dakota	46.88	-102.79	23765
Dickinson	US	Texas	29.46	-95.05	19895
Dickson	US	Tennessee	36.08	-87.39	15359
Didao	CN		45.35	130.84	109561
Didcot	GB		51.61	-1.24	29341
Dien Bien Phu	VN		21.39	103.02	84672
Dieppe	CA		46.08	-64.69	27304
Diepsloot	ZA		-25.93	28.01	350000
Diez de Octubre	CU		23.09	-82.36	227293
Diffa	NE		13.32	12.61	54082
Digos	PH		6.75	125.36	116122
Digri	PK		25.16	69.11	234578
Dihok	IQ		36.87	42.99	340900
Dijkot	PK		31.22	73.00	96934
Dijon	FR		47.31	5.01	159941
Dikirnis	EG		31.09	31.59	101082
Dili	TL		-8.56	125.57	150000
Dilling	SD		12.05	29.65	59089
Dimbokro	CI		6.65	-4.71	70198
Dimitrovgrad	RU		54.21	49.62	132226
Dimāpur	IN		25.91	93.72	135860
Din Daeng	TH		13.79	100.57	130220
Dinaig	PH		7.17	124.21	116768
Dinajpur	BD		25.63	88.64	206234
Dinalupihan	PH		14.88	120.45	66670
Dinapore	IN		25.64	85.05	152940
Dinapur Nizamat	IN		25.64	85.05	182429
Dindigul	IN		10.37	77.98	292512
Dinga	PK		32.64	73.72	89922
Dingjia	CN		29.41	106.14	60585
Dingtao	CN		35.07	115.57	58206
Dingxi	CN		35.57	104.62	420614
Dingzhou	CN		38.51	114.99	152934
Dinnington	GB		53.37	-1.20	19860
Dinslaken	DE		51.56	6.74	66993
Dinuba	US	California	36.54	-119.39	23702
Diourbel	SN		14.65	-16.24	157554
Dipalpur	PK		30.67	73.65	99858
Diphu	IN		25.84	93.43	61797
Dipolog	PH		8.57	123.33	93549
Dire Dawa	ET		9.59	41.87	343000
Dishnā	EG		26.12	32.47	64744
District of Taher	DZ		36.77	5.90	60426
Disūq	EG		31.13	30.65	149291
Divinópolis	BR		-20.14	-44.89	231091
Divo	CI		5.84	-5.36	136627
Dix Hills	US	New York	40.80	-73.34	26892
Dixiana	US	Alabama	33.74	-86.65	22940
Dixinn	GN		9.55	-13.67	137287
Dixon	US	California	38.45	-121.82	19390
Dixon	US	Illinois	41.84	-89.48	15319
Diyarb Najm	EG		30.75	31.44	80954
Diyarbakır	TR		37.91	40.22	1833684
Djelfa	DZ		34.67	3.26	265833
Djemmal	TN		35.62	10.76	55285
Djibo	BF		14.10	-1.63	61462
Djibouti	DJ		11.59	43.15	626512
Djougou	BJ		9.71	1.67	94773
Dmitrov	RU		56.34	37.52	61607
Dnipro	UA		48.47	35.04	968502
Dniprovskyi	UA		50.45	30.60	357900
Doba	TD		8.66	16.85	70942
Dobo	ID		-5.76	134.23	52104
Dobrich	BG		43.56	27.83	69434
Docklands	AU		-37.81	144.95	15495
Doddaballapura	IN		13.29	77.54	93105
Dodge City	US	Kansas	37.75	-100.02	27912
Dodoma	TZ		-6.17	35.74	765179
Dogonbadan	IR		30.36	50.80	96728
Dogondoutchi	NE		13.64	4.03	50037
Doha	QA		25.29	51.53	344939
Dohad	IN		22.83	74.26	118846
Doilungdêqên	CN		29.66	90.99	137451
Dokri	PK		27.37	68.10	125000
Dolgoprudnyy	RU		55.95	37.50	68259
Dolisie	CG		-4.20	12.67	121000
Dollard-Des Ormeaux	CA		45.49	-73.82	48930
Dolores Hidalgo	MX		21.16	-100.93	67101
Dolton	US	Illinois	41.64	-87.61	23197
Dom Eliseu	BR		-4.29	-47.51	58484
Dombivali	IN		19.22	73.08	1247327
Domodedovo	RU		55.44	37.75	53887
Dompu	ID		-8.54	118.46	54987
Don Carlos	PH		7.68	125.00	73592
Don Torcuato	AR		-34.49	-58.63	71356
Don Valley Village	CA		43.78	-79.35	27051
Donaghmede	IE		53.40	-6.16	15299
Donaustadt	AT		48.23	16.46	187007
Doncaster	GB		53.52	-1.13	113566
Doncaster	AU		-37.79	145.12	25020
Doncaster East	AU		-37.79	145.15	30926
Dondo	MZ		-19.61	34.74	82260
Dondo	AO		-9.68	14.43	64643
Dondo	AO		-9.05	15.32	64643
Donetsk	UA		48.02	37.80	901645
Donetsk	RU		48.34	39.95	50850
Dongcun	CN		36.78	121.16	92282
Dongdu	CN		35.85	117.70	72957
Dongfeng	CN		42.67	125.53	67820
Donggongon	MY		5.91	116.10	78086
Dongguan	CN		23.02	113.75	9644871
Donghae City	KR		37.54	129.11	101128
Donghai	CN		22.95	115.64	264709
Donghe	CN		32.23	106.30	81953
Dongkan	CN		34.00	119.83	72789
Dongling	CN		41.81	123.58	171454
Dongning	CN		44.08	131.12	61440
Dongola	SD		19.18	30.48	56167
Dongsheng	CN		39.82	109.98	99809
Dongtai	CN		32.85	120.31	262873
Dongxi	CN		28.76	106.66	58169
Dongxia	CN		36.75	118.58	84083
Dongxing	CN		21.55	107.97	88607
Dongyang	CN		29.27	120.23	130387
Dongying	CN		37.46	118.49	998968
Donna	US	Texas	26.17	-98.05	16523
Donostia / San Sebastián	ES		43.31	-1.97	185357
Doral	US	Florida	25.82	-80.36	75874
Dorbod	CN		46.86	124.44	55316
Dorchester	US	Massachusetts	42.30	-71.07	97826
Dorchester	GB		50.72	-2.43	16879
Dordrecht	NL		51.81	4.67	119260
Doreen	AU		-37.60	145.15	27122
Dorking	GB		51.23	-0.33	17747
Dormagen	DE		51.10	6.83	63582
Dorogomilovo	RU		55.74	37.55	68000
Dorset Park	CA		43.75	-79.28	25003
Dorsten	DE		51.66	6.97	79981
Dortmund	DE		51.51	7.47	588462
Dorval	CA		45.45	-73.75	18980
Dorūd	IR		33.49	49.06	121638
Dos Hermanas	ES		37.28	-5.92	122943
Dosquebradas	CO		4.84	-75.67	206693
Dosso	NE		13.05	3.19	79406
Dothan	US	Alabama	31.22	-85.39	68567
Douala	CM		4.05	9.70	1338082
Douane	TN		36.45	10.76	60192
Douar Hicher	TN		36.83	10.09	82532
Douglas	IE		51.87	-8.44	26883
Douglas	IM		54.15	-4.48	26218
Douglas	US	Illinois	41.83	-87.62	20323
Douglas	US	Arizona	31.34	-109.55	16592
Douglasville	US	Georgia	33.75	-84.75	32897
Dougnane	SN		14.96	-16.87	69556
Douliu	TW		23.71	120.54	107924
Dourados	BR		-22.22	-54.81	162202
Dover	GB		51.13	1.31	41709
Dover	US	Delaware	39.16	-75.52	39403
Dover	US	New Hampshire	43.20	-70.87	30880
Dover	US	New Jersey	40.88	-74.56	18346
Dovercourt-Wallace Emerson-Junction	CA		43.67	-79.44	36625
Dovzhansk	UA		48.08	39.65	62691
Downers Grove	US	Illinois	41.81	-88.01	49732
Downey	US	California	33.94	-118.13	114219
Downsview-Roding-CFB	CA		43.73	-79.49	35052
Downtown DC	US	District of Columbia	38.89	-77.02	52560
Downtown Eastside	CA		49.28	-123.09	18477
Downtown Halifax	CA		44.65	-63.58	25555
Downtown Vancouver	CA		49.28	-123.12	62030
Doğubayazıt	TR		39.55	44.08	70171
Dracut	US	Massachusetts	42.67	-71.30	28831
Drammen	NO		59.74	10.20	106013
Drancy	FR		48.93	2.45	62488
Draper	US	Utah	40.52	-111.86	46774
Drean	DZ		36.68	7.75	55147
Dresden	DE		51.05	13.74	564904
Drexel Heights	US	Arizona	32.14	-111.03	27749
Drexel Hill	US	Pennsylvania	39.95	-75.29	28043
Drobeta-Turnu Severin	RO		44.63	22.65	79865
Drogheda	IE		53.72	-6.35	44135
Drohobych	UA		49.35	23.51	73682
Droichead Nua	IE		53.18	-6.80	22742
Droitwich	GB		52.27	-2.15	23834
Dronfield	GB		53.30	-1.48	21124
Droylsden	GB		53.48	-2.15	23689
Drummondville	CA		45.88	-72.48	59489
Druzhkivka	UA		48.62	37.53	53977
Dschang	CM		5.44	10.05	99582
Duarte	US	California	34.14	-117.98	21990
Dubai	AE		25.08	55.31	3790000
Dubai Festival City	AE		25.22	55.36	77000
Dubai Investments Park	AE		25.01	55.16	160000
Dubai Marina	AE		25.09	55.15	120000
Dubai Silicon Oasis	AE		25.12	55.39	90000
Dubbo	AU		-32.24	148.60	43516
Dublin	IE		53.33	-6.25	1024027
Dublin	US	California	37.70	-121.94	57721
Dublin	US	Ohio	40.10	-83.11	45098
Dublin	US	Georgia	32.54	-82.90	16197
Dubna	RU		56.74	37.19	60604
Dubréka	GN		9.79	-13.52	182296
Dubuque	US	Iowa	42.50	-90.66	58799
Ducheng	CN		23.24	111.53	95525
Dudley	GB		52.50	-2.08	199059
Duekoué	CI		6.74	-7.35	117023
Duisburg	DE		51.43	6.77	504358
Duitama	CO		5.82	-73.03	92040
Dukinfield	GB		53.47	-2.09	21155
Dukuhturi	ID		-6.90	109.08	98074
Dullewala	PK		31.83	71.44	54277
Duluth	US	Minnesota	46.78	-92.11	86110
Duluth	US	Georgia	34.00	-84.14	29193
Dumaguete	PH		9.31	123.31	113541
Dumai	ID		1.67	101.44	349389
Dumas	US	Texas	35.87	-101.97	15001
Dumbarton	GB		55.94	-4.57	19950
Dumfries	GB		55.07	-3.61	46500
Dumont	US	New Jersey	40.94	-74.00	18001
Dumraon	IN		25.55	84.15	53618
Dumyāţ al Jadīdah	EG		31.43	31.68	54508
Dunaújváros	HU		46.96	18.94	50084
Dunbar-Southlands	CA		49.24	-123.19	21245
Duncan	US	Oklahoma	34.50	-97.96	23231
Duncan	CA		48.78	-123.70	22199
Duncanville	US	Texas	32.65	-96.91	39826
Duncraig	AU		-31.83	115.78	15982
Dundalk	US	Maryland	39.25	-76.52	63597
Dundalk	IE		54.00	-6.42	43112
Dundee	GB		56.47	-2.97	148210
Dundee	ZA		-28.17	30.23	84413
Dundo	AO		-7.37	20.82	177604
Dunedin	NZ		-45.87	170.50	132800
Dunedin	US	Florida	28.02	-82.77	36164
Dunfermline	GB		56.07	-3.46	54990
Dunhou	CN		27.05	114.90	94445
Dunhua	CN		43.37	128.23	148844
Dunhuang	CN		40.17	94.68	186027
Dunkirk	FR		51.03	2.38	86263
Dunstable	GB		51.89	-0.52	51973
Dunwoody	US	Georgia	33.95	-84.33	48733
Duoba	CN		36.66	101.53	66767
Duobao	CN		30.67	112.69	90257
Dupont Circle	US	District of Columbia	38.91	-77.04	23226
Duque de Caxias	BR		-22.79	-43.31	818329
Duramē	ET		7.23	37.88	65900
Durango	US	Colorado	37.28	-107.88	18006
Durant	US	Oklahoma	33.99	-96.37	17286
Durban	ZA		-29.86	31.03	3338026
Durbanville	ZA		-33.83	18.65	54286
Durg	IN		21.19	81.28	268806
Durgapur	IN		23.52	87.31	518872
Durham	US	North Carolina	35.99	-78.90	257636
Durham	GB		54.78	-1.58	47785
Durrës	AL		41.32	19.45	195920
Dushan	CN		25.83	107.53	80045
Dushanbe	TJ		38.54	68.78	679400
Dusit	TH		13.78	100.52	107655
Duvernay	CA		45.58	-73.67	37460
Duxbury	US	Massachusetts	42.04	-70.67	15059
Duyun	CN		26.27	107.52	198516
Duyên Hải	VN		9.63	106.49	69961
Duzhou	CN		29.88	107.08	51888
Dyer	US	Indiana	41.49	-87.52	16051
Dyersburg	US	Tennessee	36.03	-89.39	16781
Dyker Heights	US	New York	40.62	-74.01	34399
Dzerzhinsk	RU		56.24	43.46	233126
Dédougou	BF		12.46	-3.46	63617
Déressia	TD		9.76	16.27	50113
Dêqên	CN		29.96	90.72	62400
Döbling	AT		48.25	16.33	75418
Dörtyol	TR		36.84	36.23	56513
Dún Laoghaire	IE		53.29	-6.14	31239
Düren	DE		50.80	6.49	93440
Düsseldorf	DE		51.22	6.78	618685
Düzce	TR		40.84	31.16	194097
Dādri	IN		28.55	77.55	70609
Dāhānu	IN		19.97	72.71	50287
Dāmghān	IR		36.17	54.34	67694
Dār Kulayb	BH		26.07	50.50	65466
Dārayyā	SY		33.46	36.23	71596
Dārjiling	IN		27.03	88.27	123797
Dārāb	IR		28.75	54.54	70232
Dąbrowa Górnicza	PL		50.33	19.20	116971
Dĩ An	VN		10.91	106.77	463023
Dīdwāna	IN		27.40	74.58	53749
Dīla	ET		6.42	38.32	158800
Dūmā	SY		33.57	36.40	111864
Dại Mỗ	VN		20.98	105.77	59980
Eagan	US	Minnesota	44.80	-93.17	66286
Eagle	US	Idaho	43.70	-116.35	23612
Eagle Mountain	US	Utah	40.31	-112.01	27332
Eagle Pass	US	Texas	28.71	-100.50	28765
Eagle River	US	Alaska	61.32	-149.57	24793
Ealing Common	GB		51.51	-0.30	15945
Earl Shilton	GB		52.58	-1.32	19578
Earlsfield	GB		51.44	-0.19	15562
Earlwood	AU		-33.92	151.13	17592
Easley	US	South Carolina	34.83	-82.60	20765
East Amherst	US	New York	43.02	-78.70	24914
East Barnet	GB		51.65	-0.16	18100
East Boston	US	Massachusetts	42.38	-71.04	43066
East Brainerd	US	Tennessee	35.00	-85.15	15114
East Brunswick	US	New Jersey	40.43	-74.42	48495
East Chattanooga	US	Tennessee	35.07	-85.25	154024
East Chicago	US	Indiana	41.64	-87.45	28699
East Cleveland	US	Ohio	41.53	-81.58	17344
East Concord	US	New Hampshire	43.24	-71.54	42605
East Dereham	GB		52.68	0.93	19256
East Elmhurst	US	New York	40.76	-73.87	23150
East End-Danforth	CA		43.68	-79.30	21381
East Flatbush	US	New York	40.65	-73.93	178464
East Florence	US	Alabama	34.81	-87.65	35733
East Garfield Park	US	Illinois	41.88	-87.70	20656
East Grinstead	GB		51.12	-0.01	26523
East Gwillimbury	CA		44.10	-79.44	23991
East Hampton	US	Virginia	37.04	-76.33	147993
East Harlem	US	New York	40.79	-73.94	115921
East Hartford	US	Connecticut	41.78	-72.61	51252
East Hastings	CA		49.27	-123.06	80740
East Haven	US	Connecticut	41.28	-72.87	29257
East Helsinki	FI		60.21	25.08	170557
East Hemet	US	California	33.74	-116.94	17418
East Hill-Meridian	US	Washington	47.41	-122.17	29878
East Honolulu	US	Hawaii	21.29	-157.72	49914
East Independence	US	Missouri	39.10	-94.36	110675
East Jerusalem	PS		31.78	35.23	428304
East Kilbride	GB		55.76	-4.18	75310
East Lake	US	Florida	28.11	-82.69	30962
East Lake-Orient Park	US	Florida	27.98	-82.38	22753
East Lansing	US	Michigan	42.74	-84.48	48471
East London	ZA		-33.02	27.91	478676
East Longmeadow	US	Massachusetts	42.06	-72.51	15102
East Los Angeles	US	California	34.02	-118.17	126496
East Massapequa	US	New York	40.67	-73.44	19069
East Meadow	US	New York	40.71	-73.56	38132
East Millcreek	US	Utah	40.70	-111.81	20816
East Molesey	GB		51.40	-0.35	18565
East Moline	US	Illinois	41.50	-90.44	21350
East Mount Airy	US	Pennsylvania	40.06	-75.19	18516
East Naples	US	Florida	26.14	-81.77	22951
East New York	US	New York	40.67	-73.88	173198
East Northport	US	New York	40.88	-73.32	20217
East Norwalk	US	Connecticut	41.11	-73.40	84530
East Orange	US	New Jersey	40.77	-74.20	64949
East Palo Alto	US	California	37.47	-122.14	29662
East Patchogue	US	New York	40.77	-73.00	22469
East Pensacola Heights	US	Florida	30.43	-87.18	54104
East Peoria	US	Illinois	40.67	-89.58	23080
East Point	US	Georgia	33.68	-84.44	35467
East Providence	US	Rhode Island	41.81	-71.37	47408
East Rancho Dominguez	US	California	33.90	-118.20	15135
East Ridge	US	Tennessee	35.01	-85.25	20979
East Riverdale	US	Maryland	38.96	-76.91	15509
East Saint Louis	US	Illinois	38.62	-90.15	27006
East Setauket	US	New York	40.94	-73.11	17006
East Tremont	US	New York	40.85	-73.89	22886
East Village	US	New York	40.73	-73.99	62832
Eastbourne	GB		50.77	0.28	101689
Eastchester	US	New York	40.96	-73.81	19554
Easthampton	US	Massachusetts	42.27	-72.67	16611
Eastlake	US	Ohio	41.65	-81.45	18232
Eastleigh	GB		50.97	-1.35	54225
Eastmont	US	Washington	47.90	-122.18	20101
Easton	US	Pennsylvania	40.69	-75.22	26915
Easton	US	Massachusetts	42.02	-71.13	23459
Easton	US	Maryland	38.77	-76.08	16617
Eastpointe	US	Michigan	42.47	-82.96	32657
Eastvale	US	California	33.96	-117.56	59039
Eastwood	GB		53.00	-1.30	18612
Eastwood	AU		-33.79	151.08	17792
Eau Claire	US	Wisconsin	44.81	-91.50	67778
Ebbw Vale	GB		51.78	-3.21	33068
Ebetsu	JP		43.11	141.55	133953
Ebina	JP		35.38	139.40	136516
Ebute Ikorodu	NG		6.60	3.49	535619
Ecatepec de Morelos	MX		19.60	-99.06	1645352
Eccles	GB		53.48	-2.33	37275
Ech Chettia	DZ		36.20	1.26	60170
Echizen	JP		35.89	136.17	83078
Echo Park	US	California	34.08	-118.26	43832
Echuca	AU		-36.14	144.75	15056
Ecunna	AO		-12.68	15.51	82541
Edattala	IN		10.06	76.38	77811
Ede	NG		7.74	4.44	159866
Ede	NL		52.03	5.66	67670
Eden	US	North Carolina	36.49	-79.77	15403
Eden Prairie	US	Minnesota	44.85	-93.47	63496
Edenbridge-Humber Valley	CA		43.67	-79.52	15535
Edfu	EG		24.98	32.88	79510
Edgemont	CA		51.13	-114.15	15225
Edgewater	US	Illinois	41.98	-87.66	54873
Edgewater	US	Florida	28.99	-80.90	21566
Edgewood	US	Maryland	39.42	-76.29	25562
Edina	US	Minnesota	44.89	-93.35	50138
Edinburg	US	Texas	26.30	-98.16	84497
Edinburgh	GB		55.95	-3.20	514990
Edirne	TR		41.68	26.56	180002
Edison	US	New Jersey	40.52	-74.41	102548
Edmond	US	Oklahoma	35.65	-97.48	90092
Edmonds	US	Washington	47.81	-122.38	41375
Edmonds	CA		49.21	-122.94	22318
Edmonton	CA		53.55	-113.47	1010899
Edmonton	GB		51.63	-0.06	82000
Edmundston	CA		47.37	-68.33	16580
Edogawe	JP		35.69	139.87	697932
Edwardsville	US	Illinois	38.81	-89.95	24992
Edéa	CM		3.80	10.13	103861
Effium	NG		6.63	8.06	86945
Efon-Alaaye	NG		7.66	4.92	279319
Eger	HU		47.90	20.37	53876
Eggertsville	US	New York	42.96	-78.80	15019
Egham	GB		51.43	-0.55	29663
Eglinton East	CA		43.74	-79.25	22776
Egypt Lake-Leto	US	Florida	28.02	-82.51	35282
Eha Amufu	NG		6.66	7.76	70779
Eight Mile Plains	AU		-27.58	153.10	15364
Eilat	IL		29.56	34.95	52299
Eimsbüttel	DE		53.57	9.96	269118
Eindhoven	NL		51.44	5.48	235691
Eisen	KR		35.97	128.93	56006
Eisenzicken	AT		47.28	16.26	54353
Eixample	ES		41.39	2.16	266477
Ejido	VE		8.55	-71.24	120978
Ejigbo	NG		7.90	4.31	138357
Ejura	GH		7.39	-1.36	70807
Ekangala	ZA		-25.67	28.73	58099
Ekibastuz	KZ		51.72	75.32	121470
Ekpoma	NG		6.74	6.14	59618
Ekpé	BJ		6.39	2.54	75313
El Achir	DZ		36.06	4.63	158333
El Bagre	CO		7.60	-74.81	51150
El Banco	CO		9.00	-73.98	54522
El Bayadh	DZ		33.68	1.02	85577
El Cafetal	VE		10.47	-66.83	80029
El Cajon	US	California	32.79	-116.96	103679
El Camino Real	US	California	33.70	-117.78	15999
El Centro	US	California	32.79	-115.56	43956
El Cerrito	US	California	37.92	-122.31	23549
El Daein	SD		11.46	26.13	264734
El Dibir	SO		11.77	51.22	200000
El Dorado	US	Arkansas	33.21	-92.67	18386
El Dorado Hills	US	California	38.69	-121.08	42108
El Ejido	ES		36.78	-2.81	84710
El Eulma	DZ		36.15	5.69	145380
El Fasher	SD		13.63	25.35	252609
El Geneina Fort	SD		13.47	22.46	134264
El Hatillo	VE		10.42	-66.83	57591
El Jadida	MA		33.26	-8.51	212863
El Kef	TN		36.17	8.70	53596
El Kelaa des Srarhna	MA		32.05	-7.41	103982
El Khroub	DZ		36.26	6.69	90122
El Limón	VE		10.31	-67.63	148247
El Menia	DZ		30.58	2.88	57344
El Mgarsa	TN		33.82	10.99	63528
El Mirage	US	Arizona	33.61	-112.32	33935
El Monte	US	California	34.07	-118.03	116732
El Mourouj	TN		36.71	10.21	120732
El Negrito	HN		15.32	-87.70	50550
El Nido	PH		11.19	119.40	51367
El Obeid	SD		13.18	30.22	393311
El Oued	DZ		33.36	6.86	186525
El Palomar	AR		-34.62	-58.60	59031
El Paso	US	Texas	31.76	-106.49	678815
El Prat de Llobregat	ES		41.33	2.09	63418
El Progreso	HN		15.40	-87.80	100810
El Pueblito	MX		20.54	-100.44	71254
El Puerto de Santa María	ES		36.59	-6.23	88364
El Reno	US	Oklahoma	35.53	-97.96	18516
El Segundo	US	California	33.92	-118.42	17037
El Shorouk	EG		30.14	31.62	91899
El Tigre	VE		8.89	-64.25	222450
El Tocuyo	VE		9.79	-69.79	74829
El Viejo	NI		12.66	-87.17	53504
El Vigía	VE		8.61	-71.66	162289
El Wak	KE		2.81	40.93	60732
Elazığ	TR		38.67	39.22	443363
Elbasan	AL		41.11	20.08	100903
Elbistan	TR		38.21	37.20	80456
Elbląg	PL		54.15	19.41	127558
Elche	ES		38.26	-0.70	234765
Elda	ES		38.48	-0.79	55168
Eldersburg	US	Maryland	39.40	-76.95	30531
Eldorado	AR		-26.40	-54.62	54189
Eldoret	KE		0.52	35.27	475716
Electronic City Phase I	IN		12.85	77.66	76348
Elektrostal’	RU		55.79	38.46	144387
Elgin	US	Illinois	42.04	-88.28	112111
Elgin	GB		57.65	-3.32	25040
Elista	RU		46.31	44.26	106971
Elizabeth	US	New Jersey	40.66	-74.21	129007
Elizabeth City	US	North Carolina	36.29	-76.25	17988
Elizabethtown	US	Kentucky	37.69	-85.86	29678
Elk Grove	US	California	38.41	-121.37	166913
Elk Grove Village	US	Illinois	42.00	-87.97	33238
Elk River	US	Minnesota	45.30	-93.57	23963
Elkhart	US	Indiana	41.68	-85.98	52348
Elko	US	Nevada	40.83	-115.76	20279
Elkridge	US	Maryland	39.21	-76.71	15593
Elkton	US	Maryland	39.61	-75.83	15782
Elland	GB		53.69	-1.84	15625
Ellenbrook	AU		-31.77	115.97	24668
Ellendale	US	Tennessee	35.23	-89.83	25882
Ellensburg	US	Washington	47.00	-120.55	19001
Ellesmere Port Town	GB		53.28	-2.90	65430
Ellicott City	US	Maryland	39.27	-76.80	65834
Elmhurst	US	New York	40.74	-73.88	113364
Elmhurst	US	Illinois	41.90	-87.94	45957
Elmira	US	New York	42.09	-76.81	28213
Elmont	US	New York	40.70	-73.71	33198
Elmwood	US	Pennsylvania	39.92	-75.23	16988
Elmwood Park	US	Illinois	41.92	-87.81	24840
Elmwood Park	US	New Jersey	40.90	-74.12	20279
Eloise	US	Florida	27.99	-81.74	23366
Eloy	US	Arizona	32.76	-111.55	17059
Eloy Alfaro	EC		-2.17	-79.84	315724
Eltham	GB		51.45	0.05	48964
Eltham	AU		-37.73	145.15	18847
Eluru	IN		16.71	81.10	218020
Elwood	AU		-37.88	144.98	15153
Ely	GB		52.40	0.26	20574
Elyria	US	Ohio	41.37	-82.11	53775
Emalahleni	ZA		-25.87	29.23	373403
eMbalenhle	ZA		-26.53	29.07	142443
Embu	KE		-0.54	37.46	64979
Embu das Artes	BR		-23.65	-46.85	250691
Embu-Guaçu	BR		-23.83	-46.81	66970
Emden	DE		53.37	7.21	51526
Emerson Hill	US	New York	40.61	-74.10	15412
Emin	CN		46.53	83.63	57782
Eminabad	PK		32.04	74.26	150646
Eminönü	TR		41.02	28.97	55548
Emmen	NL		52.78	6.91	57010
Emmiganūr	IN		15.77	77.48	95149
Emporia	US	Kansas	38.40	-96.18	24649
Emsworth	GB		50.85	-0.94	18777
Emure-Ekiti	NG		7.44	5.46	90645
En Nedjma	DZ		35.65	-0.57	51665
Encanto	US	Arizona	33.48	-112.08	54614
Encarnación	PY		-27.33	-55.87	74983
Enchanted Hills	US	New Mexico	35.34	-106.59	87521
Encheng	CN		22.19	112.30	110921
Encinitas	US	California	33.04	-117.29	62930
Encino	US	California	34.16	-118.50	44581
Ende	ID		-8.84	121.66	87269
Endeavour Hills	AU		-37.98	145.26	24455
Enerhodar	UA		47.49	34.66	52887
Enfield	US	Connecticut	41.98	-72.59	45212
Enfield Lock	GB		51.67	-0.03	16469
Enfield Town	GB		51.65	-0.08	156858
Engadine	AU		-34.07	151.01	17141
Engels	RU		51.48	46.11	196011
Englemount-Lawrence	CA		43.72	-79.44	22372
Englewood	US	Colorado	39.65	-104.99	33082
Englewood	US	New Jersey	40.89	-73.97	28539
Englewood	US	Illinois	41.78	-87.65	26121
Enid	US	Oklahoma	36.40	-97.88	51776
Eniwa	JP		42.89	141.58	70331
Ennis	IE		52.84	-8.99	27923
Ennis	US	Texas	32.33	-96.63	19007
Enrique B. Magalona	PH		10.88	122.98	64290
Enschede	NL		52.22	6.90	153655
Ensenada	MX		31.87	-116.60	443807
Ensenada	AR		-34.86	-57.91	63978
Enshi	CN		30.30	109.48	279185
Ensley	US	Florida	30.52	-87.27	20602
Entebbe	UG		0.06	32.48	102600
Enterprise	US	Nevada	36.03	-115.24	108481
Enterprise	US	Alabama	31.32	-85.86	27978
Enugu	NG		6.44	7.50	950000
Enugu-Ukwu	NG		6.17	7.01	68785
Envigado	CO		6.18	-75.59	163007
Epe	NG		6.58	3.98	84711
Epping	AU		-37.65	145.03	33489
Epping	AU		-33.77	151.08	23435
Epsom	GB		51.33	-0.27	31489
Epsom	NZ		-36.89	174.77	20200
Epworth	ZW		-17.89	31.15	206365
Eqbālīyeh	IR		36.23	49.92	55066
Er Roseires	SD		11.87	34.39	58712
Erbaa	TR		40.67	36.57	52185
Erbil	IQ		36.19	44.01	1612700
Erciş	TR		39.03	43.36	91915
Ercolano	IT		40.81	14.35	53576
Erdaojiang	CN		41.78	126.03	60831
Erdenet	MN		49.03	104.08	97814
Erebuni	AM		40.13	44.53	129700
Erechim	BR		-27.63	-52.28	96087
Ereğli	TR		37.51	34.05	156253
Ereğli	TR		41.28	31.42	88848
Erftstadt	DE		50.81	6.79	51207
Erfurt	DE		50.98	11.04	218793
Ergani	TR		38.27	39.75	52684
Erie	US	Pennsylvania	42.13	-80.09	99475
Erie	US	Colorado	40.05	-105.05	21420
Eringate-Centennial-West Deane	CA		43.66	-79.58	18588
Erlangen	DE		49.59	11.01	102675
Erlanger	US	Kentucky	39.02	-84.60	18797
Ermelino Matarazzo	BR		-23.49	-46.47	112333
Ermelo	ZA		-26.53	29.98	100324
Erode	IN		11.34	77.73	521891
Errachidia	MA		31.93	-4.43	100870
Erskine	GB		55.90	-4.45	15530
Erzincan	TR		39.74	39.49	150714
Erzsébetváros	HU		47.50	19.07	62000
Erzurum	TR		39.91	41.28	767848
Esbjerg	DK		55.47	8.45	71698
Escada	BR		-8.36	-35.22	62252
Escalante	PH		10.84	123.50	97050
Eschweiler	DE		50.82	6.27	55778
Escondido	US	California	33.12	-117.09	151038
Escuintla	GT		14.30	-90.79	156313
Esenler	TR		41.04	28.88	520235
Esenyurt	TR		41.03	28.68	983571
Esfarāyen	IR		37.08	57.51	59490
Esher	GB		51.37	-0.37	52392
Eskilstuna	SE		59.37	16.51	67359
Eskişehir	TR		39.78	30.52	921630
Eslamshahr	IR		35.55	51.24	450000
Eslāmābād-e Gharb	IR		34.11	46.53	90559
Esmeraldas	EC		0.96	-79.65	218727
Esmeraldas	BR		-19.76	-44.31	85598
Esna	EG		25.29	32.55	462787
Espinal	CO		4.15	-74.88	56213
Espoo	FI		60.21	24.65	323910
Esquimalt	CA		48.44	-123.41	17655
Essaouira	MA		31.51	-9.77	85137
Essen	DE		51.46	7.01	593085
Essendon	AU		-37.75	144.91	21240
Essex	US	Maryland	39.31	-76.47	39262
Esslingen	DE		48.74	9.30	92390
Estancia	PH		11.46	123.15	54882
Esteio	BR		-29.86	-51.18	76137
Estelle	US	Louisiana	29.85	-90.11	16377
Estelí	NI		13.09	-86.36	96422
Estepona	ES		36.43	-5.15	67012
Estero	US	Florida	26.44	-81.81	30799
Estância	BR		-11.27	-37.44	65078
Esuk Oron	NG		4.80	8.25	112033
Etah	IN		27.56	78.66	131023
Etobicoke	CA		43.64	-79.57	365000
Ettadhamen	TN		36.83	10.11	84312
Etwatwa	ZA		-26.13	28.45	151866
Etāwa	IN		24.18	78.20	55185
Etāwah	IN		26.78	79.02	257448
Euclid	US	Ohio	41.59	-81.53	47676
Euclides da Cunha	BR		-10.51	-39.02	61456
Eugene	US	Oregon	44.05	-123.09	176654
Euless	US	Texas	32.84	-97.08	54219
Eunápolis	BR		-16.38	-39.58	113710
Eureka	US	California	40.80	-124.16	27017
Euskirchen	DE		50.66	6.79	54889
Eustis	US	Florida	28.85	-81.69	19986
Eusébio	BR		-3.89	-38.45	74170
Evans	US	Georgia	33.53	-82.13	29011
Evans	US	Colorado	40.38	-104.69	21383
Evanston	US	Illinois	42.04	-87.69	75527
Evanston	CA		51.16	-114.12	18710
Evansville	US	Indiana	37.97	-87.56	119943
Evaton	ZA		-26.53	27.85	725468
Everett	US	Washington	47.98	-122.20	108010
Everett	US	Massachusetts	42.41	-71.05	46050
Evergreen	CA		50.93	-114.10	20780
Evergreen Park	US	Illinois	41.72	-87.70	19841
Evesham	GB		52.09	-1.95	27684
Evington	GB		52.60	-1.07	17268
Ewell	GB		51.35	-0.25	39994
Ewing	US	New Jersey	40.27	-74.80	36559
Exeter	GB		50.72	-3.53	130709
Exmouth	GB		50.62	-3.40	36204
Extrema	BR		-22.85	-46.32	53482
Extremoz	BR		-5.71	-35.31	61635
Ezeiza	AR		-34.85	-58.52	115021
Ezhou	CN		30.40	114.83	193652
Ezhva	RU		61.81	50.73	56000
Ezza-Ohu	NG		6.44	8.08	67414
Ełk	PL		53.83	22.36	55769
E’zhou	CN		30.40	114.89	668727
Facatativá	CO		4.81	-74.35	141762
Fada N'gourma	BF		12.06	0.36	73200
Failsworth	GB		53.50	-2.17	20555
Fair Lawn	US	New Jersey	40.94	-74.13	33597
Fair Oaks	US	California	38.64	-121.27	30912
Fairbanks	US	Alaska	64.84	-147.72	32325
Fairborn	US	Ohio	39.82	-84.02	33452
Fairfax	US	Virginia	38.85	-77.31	24013
Fairfield	US	California	38.25	-122.04	112970
Fairfield	US	Connecticut	41.14	-73.26	59052
Fairfield	US	Ohio	39.35	-84.56	42767
Fairfield	AU		-33.87	150.95	17932
Fairfield Heights	US	Indiana	39.83	-86.38	21285
Fairhaven	US	Massachusetts	41.64	-70.90	16453
Fairhope	US	Alabama	30.52	-87.90	18730
Fairland	US	Maryland	39.08	-76.96	23681
Fairmont	US	West Virginia	39.49	-80.14	18733
Fairview	CA		49.26	-123.13	33620
Fairview Heights	US	Illinois	38.59	-89.99	16827
Fairview Park	US	Ohio	41.44	-81.86	16407
Fairwood	US	Washington	47.45	-122.16	19102
Faisalabad	PK		31.42	73.09	3800193
Falkirk	GB		56.00	-3.79	35310
Fall River	US	Massachusetts	41.70	-71.16	94000
Fallbrook	US	California	33.38	-117.25	30534
Fallingbrook	CA		45.48	-75.48	25000
Falmouth	GB		50.15	-5.07	31988
Fana	ML		12.78	-6.96	56809
Fangcheng	CN		33.26	113.00	93808
Fangchenggang	CN		21.77	108.36	276315
Fangcun	CN		34.09	117.47	54035
Fangshan	CN		39.69	116.00	97026
Fanling	HK		22.49	114.14	263200
Fanlou	CN		34.48	116.85	62859
Fano	IT		43.84	13.02	60978
Faqirwali	PK		29.47	73.03	61586
Far Rockaway	US	New York	40.61	-73.76	39189
Faranah	GN		10.04	-10.74	70181
Fardīs	IR		35.76	51.00	181174
Fareham	GB		50.85	-1.18	42210
Fargo	US	North Dakota	46.88	-96.79	118523
Faribault	US	Minnesota	44.29	-93.27	23650
Faridabad	IN		28.41	77.31	1414050
Farmers Branch	US	Texas	32.93	-96.90	32689
Farmington	US	New Mexico	36.73	-108.22	42871
Farmington	US	Connecticut	41.72	-72.83	25000
Farmington	US	Minnesota	44.64	-93.14	22731
Farmington	US	Utah	40.98	-111.89	22566
Farmington	US	Missouri	37.78	-90.42	18181
Farmington Hills	US	Michigan	42.49	-83.38	81330
Farmingville	US	New York	40.83	-73.03	15481
Farnborough	GB		51.29	-0.76	60652
Farnham	GB		51.21	-0.80	36971
Farnworth	GB		53.55	-2.40	25680
Faro	PT		37.02	-7.93	70347
Farragut	US	Tennessee	35.88	-84.15	21919
Farroupilha	BR		-29.23	-51.35	70286
Farrukhābād	IN		27.39	79.58	241152
Farshūţ	EG		26.06	32.16	71013
Faruka	PK		31.89	72.41	60000
Farīdkot	IN		30.67	74.76	87695
Farīdpur	BD		23.61	89.84	112187
Farīdpur	IN		28.21	79.54	71783
Fasā	IR		28.94	53.65	98061
Fatehjang	PK		33.56	72.64	81321
Fatehpur	IN		25.93	80.81	166480
Fatehpur	IN		27.99	74.96	92595
Fatehābād	IN		29.52	75.46	70777
Fatih	TR		41.02	28.94	356025
Fatsa	TR		41.03	37.50	82160
Fatwa	IN		25.51	85.31	50961
Faversham	GB		51.31	0.89	23024
Favoriten	AT		48.16	16.38	201882
Fayetteville	US	North Carolina	35.05	-78.88	201963
Fayetteville	US	Arkansas	36.06	-94.16	82830
Fayetteville	US	Georgia	33.45	-84.45	16990
Fazakerley	GB		53.46	-2.93	16374
Fazenda Rio Grande	BR		-25.66	-49.31	148873
Fazilka	IN		30.40	74.03	76492
Federal Way	US	Washington	47.32	-122.31	95171
Feicheng	CN		35.26	117.97	80929
Feicheng	CN		36.25	116.77	77606
Feira de Santana	BR		-12.27	-38.97	619609
Felege Neway	ET		6.30	36.88	61000
Felgueiras	PT		41.37	-8.19	58065
Felixstowe	GB		51.96	1.35	24521
Felling	GB		54.95	-1.57	34355
Feltham	GB		51.45	-0.41	63368
Fendou	CN		46.64	124.86	226298
Fengcheng	CN		29.83	107.06	175576
Fengcheng	CN		34.70	116.59	161850
Fengcheng	CN		40.45	124.07	120514
Fenggang	CN		27.55	116.21	64715
Fenghua	CN		29.66	121.41	76653
Fenghuang	CN		27.94	109.60	370000
Fengkou	CN		30.08	113.33	67139
Fengping	CN		24.40	98.52	69586
Fengrun	CN		39.83	118.14	65150
Fengshan	TW		22.63	120.36	356463
Fengxiang	CN		30.86	121.47	1140872
Fengyi	CN		25.58	100.31	61890
Feni	BD		23.01	91.40	84028
Fenshui	CN		30.72	108.08	60308
Fenway/Kenmore	US	Massachusetts	42.34	-71.10	37733
Fenyi	CN		27.81	114.67	58478
Feodosiya	UA		45.03	35.38	68562
Ferencváros	HU		47.48	19.09	59056
Fergana	UZ		40.38	71.78	299200
Fergus	CA		43.71	-80.38	20767
Ferguson	US	Missouri	38.74	-90.31	21059
Feriana	TN		34.95	8.57	75000
Ferizaj	XK		42.37	21.16	59504
Ferkessédougou	CI		9.59	-5.19	72476
Fern Creek	US	Kentucky	38.16	-85.59	18409
Fernando de la Mora	PY		-25.34	-57.52	120167
Fernandópolis	BR		-20.28	-50.25	71186
Ferndale	US	Michigan	42.46	-83.13	20177
Ferndale	US	Maryland	39.18	-76.64	16746
Ferndown	GB		50.81	-1.90	17650
Fernley	US	Nevada	39.61	-119.25	19418
Ferntree Gully	AU		-37.88	145.30	27398
Ferrara	IT		44.84	11.62	132009
Ferraz de Vasconcelos	BR		-23.54	-46.37	179198
Ferrol	ES		43.48	-8.23	66799
Ferry Pass	US	Florida	30.51	-87.21	28921
Fes	MA		34.03	-5.00	1191905
Fethiye	TR		36.64	29.13	60437
Fianarantsoa	MG		-21.45	47.09	203105
Fichē	ET		9.80	38.73	57100
Fiddlesticks	CA		43.39	-80.29	17576
Fiditi	NG		7.71	3.92	71461
Fier	AL		40.73	19.56	56297
Fier-Çifçi	AL		40.72	19.57	60995
Fili	RU		55.75	37.49	80000
Fillmore	US	California	34.40	-118.92	15548
Financial District	US	New York	40.71	-74.01	60976
Finchley	GB		51.60	-0.20	65812
Findlay	US	Ohio	41.04	-83.65	41149
Finglas	IE		53.39	-6.30	19768
Finlyandskiy	RU		59.97	30.36	72292
Finote Selam	ET		10.70	37.27	58400
Firozpur	IN		30.93	74.61	110313
Fishers	US	Indiana	39.96	-86.01	76794
Fishtown	US	Pennsylvania	39.97	-75.14	16307
Fitchburg	US	Massachusetts	42.58	-71.80	40545
Fitchburg	US	Wisconsin	42.96	-89.47	27996
Five Corners	US	Washington	45.68	-122.58	18159
Flagami	US	Florida	25.76	-80.32	50834
Flagstaff	US	Arizona	35.20	-111.65	70320
Flatbush	US	New York	40.65	-73.96	93361
Flatlands	US	New York	40.62	-73.93	63601
Fleet	GB		51.28	-0.83	38726
Fleetwood	CA		49.17	-122.80	65565
Fleetwood	GB		53.93	-3.01	26232
Fleming Island	US	Florida	30.09	-81.72	27126
Flemingdon Park	CA		43.72	-79.33	21933
Flensburg	DE		54.79	9.44	85838
Flint	US	Michigan	43.01	-83.69	98310
Flint	GB		53.24	-3.13	26442
Floral Park	US	New York	40.72	-73.70	15969
Florence	IT		43.78	11.25	367150
Florence	US	Alabama	34.80	-87.68	40026
Florence	US	South Carolina	34.20	-79.76	38228
Florence	US	Kentucky	39.00	-84.63	32227
Florence	US	Arizona	33.03	-111.39	31110
Florence-Graham	US	California	33.97	-118.24	63387
Florencia	CO		1.62	-75.60	168346
Floriano	BR		-6.77	-43.02	62036
Florianópolis	BR		-27.60	-48.55	508826
Florida	CU		21.53	-78.23	63007
Florida Ridge	US	Florida	27.58	-80.39	18164
Floridablanca	CO		7.06	-73.09	267591
Floridsdorf	AT		48.25	16.40	162779
Florin	US	California	38.50	-121.41	47513
Florissant	US	Missouri	38.79	-90.32	52268
Flower Mound	US	Texas	33.01	-97.10	71253
Flowing Wells	US	Arizona	32.29	-111.01	16419
Flying Fish Cove	CX		-10.42	105.68	500
Fnidek	MA		35.85	-5.36	84558
Fochville	ZA		-26.49	27.49	62416
Focșani	RO		45.70	27.18	66648
Foggia	IT		41.46	15.55	137032
Foggy Bottom	US	District of Columbia	38.90	-77.06	22146
Foley	US	Alabama	30.41	-87.68	17218
Foligno	IT		42.95	12.70	56918
Folkestone	GB		51.08	1.17	66429
Folsom	US	California	38.68	-121.18	76375
Fond du Lac	US	Wisconsin	43.77	-88.44	42933
Fontana	US	California	34.09	-117.44	212704
Fontanar	CU		23.02	-82.41	178601
Fontenay-sous-Bois	FR		48.85	2.48	52075
Foothill Farms	US	California	38.68	-121.35	33121
Footscray	AU		-37.80	144.90	17131
Forbesganj	IN		26.30	87.27	50475
Fordham	US	New York	40.86	-73.90	94678
Fordon	PL		53.15	18.17	70000
Fords	US	New Jersey	40.53	-74.32	15187
Forest	BE		50.82	4.33	56254
Forest Grove	US	Oregon	45.52	-123.11	24457
Forest Heights	CA		43.42	-80.52	15581
Forest Hills	US	New York	40.72	-73.85	67714
Forest Hills	US	Michigan	42.96	-85.49	25867
Forest Lake	AU		-27.63	152.97	22581
Forest Lake	US	Minnesota	45.28	-92.99	19618
Forest Park	US	Georgia	33.62	-84.37	19383
Forest Park	US	Ohio	39.29	-84.50	18676
Forlì	IT		44.22	12.04	116696
Formby	GB		53.56	-3.07	23329
Formiga	BR		-20.46	-45.43	68248
Formosa	AR		-26.18	-58.17	222226
Formosa	BR		-15.54	-47.33	115901
Forney	US	Texas	32.75	-96.47	18418
Fort Abbas	PK		29.19	72.86	83192
Fort Beaufort	ZA		-32.77	26.63	58419
Fort Bragg	US	North Carolina	35.14	-79.01	29183
Fort Cavazos	US	Texas	31.13	-97.78	29589
Fort Collins	US	Colorado	40.59	-105.08	170924
Fort Dodge	US	Iowa	42.50	-94.17	24649
Fort Erie	CA		42.90	-78.93	30710
Fort Garry South	CA		49.79	-97.16	65420
Fort Hamilton	US	New York	40.62	-74.03	28966
Fort Hunt	US	Virginia	38.73	-77.06	16045
Fort Lauderdale	US	Florida	26.12	-80.14	183146
Fort Lee	US	New Jersey	40.85	-73.97	36672
Fort Leonard Wood	US	Missouri	37.71	-92.16	15061
Fort McMurray	CA		56.73	-111.38	66573
Fort Myers	US	Florida	26.62	-81.84	74013
Fort Pierce	US	Florida	27.45	-80.33	44484
Fort Portal	UG		0.66	30.27	60800
Fort Smith	US	Arkansas	35.39	-94.40	88194
Fort St. John	CA		56.25	-120.85	21465
Fort Thomas	US	Kentucky	39.08	-84.45	16398
Fort Walton Beach	US	Florida	30.42	-86.62	21817
Fort Washington	US	Maryland	38.71	-77.02	23717
Fort Wayne	US	Indiana	41.13	-85.13	260326
Fort William	GB		56.82	-5.11	15757
Fort Worth	US	Texas	32.73	-97.32	1008106
Fort-de-France	MQ		14.60	-61.07	89995
Fortaleza	BR		-3.72	-38.54	2400000
Fortechnyi	UA		48.50	32.25	167451
Fortuna Foothills	US	Arizona	32.66	-114.41	26265
Foshan	CN		23.03	113.13	9042509
Foster City	US	California	37.56	-122.27	33477
Foumban	CM		5.73	10.90	130287
Foumbot	CM		5.51	10.63	74319
Fountain	US	Colorado	38.68	-104.70	27767
Fountain Hills	US	Arizona	33.61	-111.72	23899
Fountain Valley	US	California	33.71	-117.95	56987
Fountainebleau	US	Florida	25.77	-80.35	59764
Four Corners	US	Florida	28.33	-81.65	26116
Four Corners	US	Oregon	44.93	-122.98	15947
Fox Chase	US	Pennsylvania	40.08	-75.08	19730
Foz do Iguaçu	BR		-25.55	-54.59	297352
Fraijanes	GT		14.47	-90.44	58922
Framingham	US	Massachusetts	42.28	-71.42	68318
Framingham Center	US	Massachusetts	42.30	-71.44	65413
Franca	BR		-20.54	-47.40	358539
Franceville	GA		-1.63	13.58	132895
Francisco Beltrão	BR		-26.08	-53.05	96666
Francisco Morato	BR		-23.28	-46.75	165139
Francistown	BW		-21.17	27.51	103417
Franco da Rocha	BR		-23.32	-46.73	144849
Franconia	US	Virginia	38.78	-77.15	18245
Frankford	US	Pennsylvania	40.01	-75.08	23503
Frankford	US	Maryland	39.33	-76.54	17135
Frankfort	US	Kentucky	38.20	-84.87	28391
Frankfort	US	Illinois	41.50	-87.85	18653
Frankfort	US	Indiana	40.28	-86.51	16060
Frankfurt (Oder)	DE		52.35	14.55	57107
Frankfurt am Main	DE		50.12	8.68	650000
Franklin	US	Tennessee	35.93	-86.87	72639
Franklin	US	Wisconsin	42.89	-88.04	36222
Franklin	US	Massachusetts	42.08	-71.40	30636
Franklin	US	Indiana	39.48	-86.05	24598
Franklin Park	US	Illinois	41.94	-87.87	18312
Franklin Square	US	New York	40.71	-73.68	29320
Frankston	AU		-38.14	145.12	37331
Frankston East	AU		-38.13	145.13	34457
Frankston South	AU		-38.17	145.14	18801
Fraser Heights	CA		49.20	-122.78	25000
Frechen	DE		50.91	6.81	52309
Frederick	US	Maryland	39.41	-77.41	69479
Fredericksburg	US	Virginia	38.30	-77.46	28118
Frederickson	US	Washington	47.10	-122.36	18719
Fredericton	CA		45.95	-66.67	63116
Fredericton Northside	CA		45.98	-66.64	28167
Frederiksberg	DK		55.68	12.53	95029
Fredrikstad	NO		59.22	10.93	83761
Freeport	US	New York	40.66	-73.58	43334
Freeport	US	Illinois	42.30	-89.62	24476
Freetown	SL		8.49	-13.24	802639
Freguesia do Ó	BR		-23.50	-46.70	137240
Freiburg	DE		48.00	7.85	237460
Fremont	US	California	37.55	-121.99	232206
Fremont	US	Nebraska	41.43	-96.50	26474
Fremont	US	Ohio	41.35	-83.12	16297
Fresh Meadows	US	New York	40.73	-73.79	28397
Fresnillo	MX		23.17	-102.87	143281
Fresno	US	California	36.75	-119.77	542107
Fresno	US	Texas	29.54	-95.45	19069
Fria	GN		10.37	-13.58	64169
Fridley	US	Minnesota	45.09	-93.26	27713
Friedrichsfelde	DE		52.51	13.51	55423
Friedrichshafen	DE		47.66	9.48	58403
Friedrichshain	DE		52.52	13.45	117829
Friendswood	US	Texas	29.53	-95.20	38800
Friern Barnet	GB		51.61	-0.16	17250
Frinton-on-Sea	GB		51.83	1.24	16941
Frisco	US	Texas	33.15	-96.82	154407
Frome	GB		51.23	-2.32	26203
Front Royal	US	Virginia	38.92	-78.19	15070
Frontera	MX		26.93	-101.45	69462
Fruit Cove	US	Florida	30.11	-81.64	29362
Frutal	BR		-20.02	-48.94	58588
Fryazevo	RU		55.73	38.46	53212
Fryazino	RU		55.96	38.05	52255
Fréjus	FR		43.43	6.74	53098
Frýdek-Místek	CZ		49.68	18.35	53590
Fuchū	JP		35.67	139.48	262790
Fuchū	JP		34.39	132.51	51155
Fuchūchō	JP		34.57	133.24	50746
Fuding	CN		27.33	120.21	192352
Fuefuki	JP		35.64	138.64	69463
Fuencarral	ES		40.50	-3.68	238765
Fuencarral-El Pardo	ES		40.50	-3.73	220085
Fuengirola	ES		36.54	-4.62	71482
Fuenlabrada	ES		40.28	-3.79	190496
Fuentes del Valle	MX		19.63	-99.14	74087
Fujairah	AE		25.12	56.34	118933
Fuji	JP		35.17	138.68	245392
Fuji	CN		29.15	105.37	131927
Fujieda	JP		34.87	138.27	145032
Fujiidera	JP		34.57	135.60	63688
Fujimino	JP		35.90	139.52	113597
Fujin	CN		47.25	132.03	89442
Fujinomiya	JP		35.22	138.62	132507
Fujioka	JP		36.25	139.07	64539
Fujisawa	JP		35.35	139.48	439728
Fukayachō	JP		36.20	139.28	141268
Fukuchiyama	JP		35.30	135.12	77306
Fukui-shi	JP		36.06	136.22	262328
Fukuoka	JP		33.60	130.42	1612392
Fukuroi	JP		34.75	137.92	88395
Fukushima	JP		37.75	140.47	294237
Fukutsu	JP		33.78	130.49	67033
Fukuyama	JP		34.48	133.37	468812
Fulda	DE		50.55	9.68	63760
Fulham	GB		51.48	-0.20	87161
Fuling	CN		29.71	107.39	268658
Fullerton	US	California	33.87	-117.93	140847
Fulwood	GB		53.35	-1.55	18233
Funafuti	TV		-8.52	179.19	6320
Funchal	PT		32.67	-16.93	105795
Fundación	CO		10.52	-74.19	59175
Fungurume	CD		-10.62	26.32	50100
Funtua	NG		11.52	7.31	136811
Funza	CO		4.72	-74.21	116890
Fuorigrotta	IT		40.83	14.20	76521
Fuqing	CN		25.73	119.37	67397
Fuquay-Varina	US	North Carolina	35.58	-78.80	23907
Furukawa	JP		38.57	140.96	76312
Furzedown	GB		51.42	-0.15	15504
Fusagasugá	CO		4.34	-74.36	88820
Fushun	CN		41.89	123.94	1400646
Fussa	JP		35.74	139.32	56786
Futtsu	JP		35.31	139.82	51650
Fuwwah	EG		31.20	30.55	93392
Fuxin	CN		42.02	121.66	689050
Fuyang	CN		32.90	115.82	1768947
Fuyang	CN		30.05	119.95	70183
Fuyu	CN		45.18	124.82	138704
Fuyu	CN		47.79	124.46	75147
Fuzhou	CN		26.06	119.31	3740000
Fuzhou	CN		27.96	116.33	1089888
Fu’an	CN		27.09	119.64	154439
Fylde	GB		53.83	-2.92	76500
Fyzābād	IN		26.78	82.15	153047
Fès al Bali	MA		34.07	-4.95	156000
Fünfhaus	AT		48.20	16.32	76396
Fürth	DE		49.48	10.99	132036
Fāqūs	EG		30.73	31.80	116945
Fīrozābād	IN		27.15	78.40	306409
Fīrūzābād	IR		28.84	52.57	65417
Fūlād Shahr	IR		32.49	51.40	88426
Ga-Rankuwa	ZA		-25.62	27.99	90945
Gaalkacyo	SO		6.77	47.43	61200
Gabela	AO		-10.85	14.38	116903
Gaborone	BW		-24.65	25.91	246325
Gabès	TN		33.88	10.10	110075
Gadag	IN		15.43	75.63	172612
Gadag-Betageri	IN		15.42	75.62	172813
Gaddi Annaram	IN		17.37	78.52	53622
Gadsden	US	Alabama	34.01	-86.01	36084
Gadwāl	IN		16.24	77.80	63177
Gafsa	TN		34.42	8.78	95242
Gage Park	US	Illinois	41.80	-87.70	41202
Gagnoa	CI		6.13	-5.95	277044
Gahanna	US	Ohio	40.02	-82.88	34590
Gainesville	US	Florida	29.65	-82.32	145214
Gainesville	US	Georgia	34.30	-83.82	38712
Gainesville	US	Texas	33.63	-97.13	16292
Gainsborough	GB		53.38	-0.77	20537
Gaithersburg	US	Maryland	39.14	-77.20	67456
Gajraula	IN		28.85	78.24	50380
Gajuwaka	IN		17.70	83.22	258944
Galaţi	RO		45.44	28.05	217851
Galesburg	US	Illinois	40.95	-90.37	31273
Galesong	ID		-5.32	119.37	83050
Gallarate	IT		45.66	8.79	50439
Gallatin	US	Tennessee	36.39	-86.45	34334
Galle	LK		6.05	80.21	93118
Gallup	US	New Mexico	35.53	-108.74	23240
Galt	US	California	38.25	-121.30	25303
Galveston	US	Texas	29.30	-94.80	50180
Galway	IE		53.27	-9.05	85910
Galátsi	GR		38.02	23.75	59345
Gama	BR		-16.03	-48.07	139467
Gama	AO		-8.57	13.48	66202
Gamagōri	JP		34.83	137.23	80063
Gambat	PK		27.35	68.52	93884
Gamboru	NG		12.37	14.21	84672
Gambēla	ET		8.25	34.58	97600
Gamonal	ES		42.36	-3.67	60000
Gamping Lor	ID		-7.80	110.33	66110
Ganda	AO		-13.02	14.64	65000
Gandajika	CD		-6.75	23.95	208051
Gandhinagar	IN		23.22	72.68	292797
Gandia	ES		38.97	-0.18	73829
Gangavati	IN		15.43	76.53	114642
Gangneung	KR		37.75	128.87	208161
Gangoh	IN		29.78	77.26	59519
Gangshang	CN		34.52	118.12	51114
Gangtok	IN		27.33	88.61	100286
Gangu Chengguanzhen	CN		34.74	105.33	103589
Gangāpur	IN		26.47	76.72	120115
Gangārāmpur	IN		25.40	88.53	65316
Ganja	AZ		40.68	46.36	330663
Gannan	CN		47.92	123.50	59239
Ganshui	CN		28.74	106.71	65994
Ganta	LR		7.24	-8.98	63523
Gantang	CN		27.44	111.97	90000
Ganzhou	CN		25.85	114.93	1977253
Gao	ML		16.27	-0.04	133110
Gaogou	CN		34.02	119.19	56214
Gaojing	CN		31.32	121.48	127512
Gaoliu	CN		36.80	118.50	67339
Gaomi	CN		36.38	119.75	391986
Gaoping	CN		30.78	106.10	204368
Gaoyou	CN		32.79	119.44	90911
Gaozhou	CN		21.92	110.86	292164
Gapan	PH		15.31	120.95	129610
Gapyeong	KR		37.83	127.51	55415
Garanhuns	BR		-8.88	-36.50	151064
Garbsen	DE		52.41	9.59	63355
García	MX		25.80	-100.59	93641
Garden City	US	Kansas	37.97	-100.87	27005
Garden City	US	Michigan	42.33	-83.33	26920
Garden City	US	New York	40.73	-73.63	22612
Garden Grove	US	California	33.77	-117.94	175393
Gardena	US	California	33.89	-118.31	60447
Gardez	AF		33.60	69.23	103601
Gardner	US	Kansas	38.81	-94.93	20868
Gardner	US	Massachusetts	42.58	-72.00	20333
Gare	FR		48.83	2.38	75580
Garfield	US	New Jersey	40.88	-74.11	31802
Garfield Heights	US	Ohio	41.42	-81.61	28097
Garhchiroli	IN		20.18	80.01	54152
Garhi Khairo	PK		28.06	67.98	193297
Garissa	KE		-0.45	39.65	163399
Garland	US	Texas	32.91	-96.64	236897
Garner	US	North Carolina	35.71	-78.61	28053
Garoowe	SO		8.40	48.48	57300
Garston	GB		53.33	-2.90	21403
Garut	ID		-7.25	107.92	131809
Gary	US	Indiana	41.59	-87.35	77156
Gashua	NG		12.87	11.04	125817
Gaspar	BR		-26.93	-48.96	72570
Gasteiz / Vitoria	ES		42.85	-2.67	257407
Gastonia	US	North Carolina	35.26	-81.19	74543
Gatchina	RU		59.58	30.13	89761
Gates-North Gates	US	New York	43.17	-77.70	15138
Gateshead	GB		54.96	-1.60	77649
Gatesville	US	Texas	31.44	-97.74	15724
Gatineau	CA		45.48	-75.70	300045
Gautier	US	Mississippi	30.39	-88.61	18570
Gawler	AU		-34.60	138.75	20006
Gaya	IN		24.80	85.00	474093
Gaya	NE		11.88	3.45	61533
Gaza	PS		31.50	34.47	410000
Gaziantep	TR		37.06	37.38	2222415
Gazipur	BD		24.00	90.42	2674697
Gbadolite	CD		4.28	21.00	73835
Gbarnga	LR		7.00	-9.47	86031
Gbawe	GH		5.58	-0.31	86718
Gboko	NG		7.32	9.00	365000
Gbongan	NG		7.48	4.35	139485
Gdańsk	PL		54.35	18.65	487371
Gdynia	PL		54.52	18.53	257000
Gebiley	SO		9.70	43.62	77320
Gebze	TR		40.80	29.43	281436
Gedangan	ID		-7.39	112.73	79230
Geelong	AU		-38.15	144.36	282809
Geita	TZ		-2.87	32.23	318006
Gejiu	CN		23.36	103.15	136135
Gela	IT		37.07	14.24	75001
Gelan	CN		30.04	107.12	55938
Gelang Patah	MY		1.45	103.59	64375
Gelendzhik	RU		44.58	38.07	50715
Gelligaer	GB		51.66	-3.26	17376
Gelsenkirchen	DE		51.51	7.10	270028
Gemena	CD		3.26	19.77	197159
Gemlik	TR		40.43	29.16	71063
General Pico	AR		-35.66	-63.76	66805
General Roca	AR		-39.03	-67.58	73212
General Santos	PH		6.11	125.17	722059
General Trias	PH		14.39	120.88	96022
Geneva	CH		46.20	6.15	201741
Geneva	US	Illinois	41.89	-88.31	21806
Gengqing	CN		31.82	98.58	88542
Genhe	CN		50.78	121.52	73631
Genk	BE		50.97	5.50	63666
Genoa	IT		44.40	8.94	580097
Gent	BE		51.05	3.72	265086
Genteng	ID		-8.37	114.15	79652
Geoje	KR		34.81	128.71	232921
George	ZA		-33.96	22.46	188580
George Town	MY		5.41	100.34	158336
George Town	KY		19.29	-81.37	29370
Georgetown	GY		6.80	-58.16	235017
Georgetown	US	Texas	30.63	-97.68	63716
Georgetown	CA		43.65	-79.92	44058
Georgetown	US	Kentucky	38.21	-84.56	32356
Georgiyevsk	RU		44.15	43.47	72649
Gera	DE		50.88	12.08	104659
Geraldton	AU		-28.78	114.61	38595
Gereida	SD		11.28	25.14	120000
Germantown	US	Maryland	39.17	-77.27	86395
Germantown	US	Tennessee	35.09	-89.81	39240
Germantown	US	Wisconsin	43.23	-88.11	19993
Germiston	ZA		-26.23	28.18	255863
Gerrards Cross	GB		51.59	-0.56	20633
Gesundbrunnen	DE		52.55	13.39	93862
Getafe	ES		40.31	-3.73	187525
Getxo	ES		43.36	-3.01	80770
Geylang	SG		1.32	103.89	110201
Ghardaïa	DZ		32.49	3.67	142913
Gharroli	IN		28.62	77.33	92540
Ghazieh	LB		33.52	35.37	50000
Ghazni	AF		33.55	68.42	141000
Ghazīpur	IN		25.58	83.59	103095
Ghotki	PK		28.00	69.32	119879
Ghulja	CN		43.92	81.32	269158
Ghātāl	IN		22.66	87.73	54658
Ghāziābād	IN		28.67	77.44	1199191
Gia Lâm	VN		21.02	105.94	309353
Gia Nghĩa	VN		12.00	107.69	85082
Gibraltar	GI		36.14	-5.35	26544
Gießen	DE		50.59	8.68	89179
Gifu	JP		35.42	136.76	402557
Gijang	KR		35.24	129.21	176388
Gijón	ES		43.54	-5.66	271780
Gilbert	US	Arizona	33.35	-111.79	247542
Gilgil	KE		-0.50	36.32	60711
Gilgit	PK		35.92	74.31	216760
Gillette	US	Wyoming	44.29	-105.50	32649
Gillingham	GB		51.39	0.55	101187
Gilroy	US	California	37.01	-121.57	53231
Gimbi	ET		9.17	35.83	64300
Gimcheon	KR		36.12	128.12	150000
Gimpo-si	KR		37.62	126.71	203391
Gingoog	PH		8.83	125.10	138895
Ginowan	JP		26.26	127.76	100125
Gion	JP		34.43	132.47	68713
Girardot City	CO		4.30	-74.81	107324
Giresun	TR		40.92	38.39	125682
Girga	EG		26.34	31.89	151256
Giridih	IN		24.19	86.31	114533
Girona	ES		41.98	2.82	100266
Girón	CO		7.07	-73.17	108466
Gisborne	NZ		-38.65	178.00	38100
Gisenyi	RW		-1.70	29.26	172357
Gitarama	RW		-2.07	29.76	87613
Gitega	BI		-3.43	29.92	64904
Githunguri	KE		-1.06	36.78	63319
Githunguri	KE		-1.30	36.99	63319
Giugliano in Campania	IT		40.93	14.20	80269
Giurgiu	RO		43.89	25.96	54551
Givatayim	IL		32.07	34.81	60644
Giza	EG		30.01	31.21	4367343
Giá Rai	VN		9.23	105.46	145340
Gjakovë	XK		42.38	20.43	94158
Gjilan	XK		42.46	21.47	51912
Glace Bay	CA		46.20	-59.96	16915
Gladbeck	DE		51.57	6.99	75499
Gladstone	AU		-23.85	151.26	45185
Gladstone	US	Missouri	39.20	-94.55	26861
Glasgow	GB		55.87	-4.26	626410
Glassboro	US	New Jersey	39.70	-75.11	19216
Glassmanor	US	Maryland	38.82	-77.00	17295
Glastonbury	US	Connecticut	41.71	-72.61	31876
Glazov	RU		58.14	52.66	100676
Glen Avon	US	California	34.01	-117.48	20199
Glen Burnie	US	Maryland	39.16	-76.62	67639
Glen Cove	US	New York	40.86	-73.63	27400
Glen Ellyn	US	Illinois	41.88	-88.07	28201
Glen Iris	AU		-37.87	145.07	26131
Glen Parva	GB		52.59	-1.17	17189
Glen Waverley	AU		-37.88	145.16	42642
Glendale	US	Arizona	33.54	-112.19	240126
Glendale	US	California	34.14	-118.26	201020
Glendale	US	New York	40.70	-73.89	34389
Glendale Heights	US	Illinois	41.91	-88.06	34208
Glendora	US	California	34.14	-117.87	52009
Glenferrie	AU		-37.83	145.05	21177
Glenfield-Jane Heights	CA		43.75	-79.51	30491
Glenmore Park	AU		-33.79	150.67	22863
Glenrothes	GB		56.20	-3.17	38360
Glenroy	AU		-37.70	144.93	23792
Glenvar Heights	US	Florida	25.71	-80.33	16898
Glenview	US	Illinois	42.07	-87.79	47446
Glenville	US	New York	42.93	-74.05	29326
Glenville	US	Ohio	41.53	-81.62	23559
Glenwood	AU		-33.73	150.93	16040
Gliwice	PL		50.30	18.68	198835
Glogovac	XK		42.63	20.89	58579
Glossop	GB		53.44	-1.95	17825
Gloucester	CA		45.35	-75.63	150012
Gloucester	GB		51.87	-2.24	132416
Gloucester	US	Massachusetts	42.61	-70.66	29781
Gloversville	US	New York	43.05	-74.34	15023
Glyfáda	GR		37.86	23.76	87305
Gniezno	PL		52.53	17.58	70269
Goba	ET		7.02	39.98	66500
Gobernador Gálvez	AR		-33.03	-60.64	74650
Gobichettipalayam	IN		11.45	77.44	59523
Gobindgarh	IN		30.67	76.30	82266
Godalming	GB		51.19	-0.61	22689
Gode	ET		5.95	43.55	67900
Godean	ID		-7.77	110.29	63164
Godfrey	US	Illinois	38.96	-90.19	17759
Godhra	IN		22.78	73.61	143644
Godomè	BJ		6.39	2.35	253262
Gohad	IN		26.43	78.44	58939
Gohāna	IN		29.14	76.70	65708
Goiana	BR		-7.56	-35.00	85160
Goianira	BR		-16.50	-49.43	71916
Goianésia	BR		-15.32	-49.12	73707
Goiânia	BR		-16.68	-49.25	1536097
Gojra	PK		31.15	72.68	214000
Gokak	IN		16.17	74.82	79121
Gokalpur	IN		28.70	77.29	121870
Gola Gokarannāth	IN		28.08	80.47	58986
Golborne	GB		53.48	-2.60	24021
Gold Coast	AU		-28.00	153.43	640778
Golden	US	Colorado	39.76	-105.22	20330
Golden Gate	US	Florida	26.19	-81.70	23961
Golden Glades	US	Florida	25.91	-80.20	33145
Golden Triangle	US	District of Columbia	38.91	-77.04	17674
Golden Valley	US	Minnesota	45.01	-93.35	21270
Golders Green	GB		51.58	-0.20	18818
Goldsboro	US	North Carolina	35.38	-77.99	35826
Golestān	IR		35.52	51.18	240000
Goleta	US	California	34.44	-119.83	30944
Golfe	AO		-8.87	13.26	655796
Golpāyegān	IR		33.45	50.29	58936
Gol’yanovo	RU		55.82	37.81	158000
Goma	CD		-1.67	29.23	432587
Gombe	NG		10.29	11.17	560000
Gombong	ID		-7.61	109.51	50950
Gonaïves	HT		19.45	-72.69	84961
Gonbad-e Kāvūs	IR		37.25	55.17	151910
Gondal	IN		21.96	70.80	112197
Gonder	ET		12.60	37.47	466000
Gondiā	IN		21.46	80.19	132813
Gondā City	IN		27.13	81.95	133583
Gongchangling	CN		41.12	123.45	70761
Gongguan	CN		21.80	109.60	96492
Gongheyong	CN		22.76	113.79	204881
Gongju	KR		36.46	127.12	72435
Gongyi	CN		34.76	113.01	56033
Gongzhuling	CN		43.50	124.82	140909
Goodings Grove	US	Illinois	41.63	-87.93	18569
Goodlettsville	US	Tennessee	36.32	-86.71	16994
Goodyear	US	Arizona	33.44	-112.36	79003
Goole	GB		53.70	-0.88	20810
Goose Creek	US	South Carolina	32.98	-80.03	40633
Gopālganj	IN		26.47	84.44	67339
Gopālganj	BD		23.22	90.06	51346
Gorakhpur	IN		29.45	75.67	1324570
Gorakhpur	IN		26.77	83.37	674246
Gordon Head	CA		48.48	-123.32	21270
Gorgān	IR		36.84	54.44	244937
Gorno-Altaysk	RU		51.96	85.92	63214
gorod Solnetchnogorsk	RU		56.19	36.98	62000
Gorontalo	ID		0.54	123.06	205390
Gorseinon	GB		51.67	-4.04	20581
Gorzów Wielkopolski	PL		52.73	15.23	114567
Gosforth	GB		55.00	-1.62	23975
Goshen	US	Indiana	41.58	-85.83	32983
Goshogawara	JP		40.80	140.44	53576
Gosnells	AU		-32.08	116.01	21149
Gosport	GB		50.80	-1.13	81952
Gostivar	MK		41.80	20.91	50974
Gotemba	JP		35.32	138.94	86614
Gothenburg	SE		57.71	11.97	608462
Gouda	NL		52.02	4.71	71952
Goulburn	AU		-34.75	149.72	24565
Governador Valadares	BR		-18.85	-41.95	250878
Goya	AR		-29.14	-59.26	70245
Goyang-si	KR		37.66	126.83	1061752
Goyerkāta	IN		26.70	89.03	66358
Goz Beida	TD		12.23	21.41	58941
Goālpāra	IN		26.18	90.63	53430
Gqeberha	ZA		-33.96	25.61	1050078
Graaff Reinet	ZA		-32.25	24.53	62896
Grafton	AU		-29.68	152.93	19255
Grafton	US	Massachusetts	42.21	-71.69	16583
Graham	US	Washington	47.05	-122.29	23491
Grahamstown	ZA		-33.30	26.53	91548
Grajaú	BR		-23.77	-46.67	384873
Grajaú	BR		-5.82	-46.14	73872
Gramercy Park	US	New York	40.74	-73.99	27988
Granada	ES		37.19	-3.61	233532
Granada	NI		11.93	-85.95	89409
Granada	CO		3.55	-73.71	68876
Granby	CA		45.40	-72.73	66222
Grand Boulevard	US	Illinois	41.81	-87.62	22373
Grand Forks	US	North Dakota	47.93	-97.03	57011
Grand Island	US	Nebraska	40.93	-98.34	51440
Grand Island	US	New York	43.03	-78.96	20813
Grand Junction	US	Colorado	39.06	-108.55	60358
Grand Prairie	US	Texas	32.75	-97.00	187809
Grand Rapids	US	Michigan	42.96	-85.67	195097
Grand-Bassam	CI		5.21	-3.74	96797
Grande Prairie	CA		55.17	-118.80	70385
Grandview	US	Missouri	38.89	-94.53	25256
Grandview-Woodlands	CA		49.28	-123.07	29175
Grandville	US	Michigan	42.91	-85.76	15953
Grangemouth	GB		56.01	-3.72	16120
Granger	US	Indiana	41.75	-86.11	30465
Granite Bay	US	California	38.76	-121.16	20402
Granite City	US	Illinois	38.70	-90.15	29054
Graniteville	US	New York	40.62	-74.15	15272
Granja	BR		-3.12	-40.83	53344
Granollers	ES		41.61	2.29	60981
Grantham	GB		52.91	-0.64	44580
Grants Pass	US	Oregon	42.44	-123.33	37088
Granville	AU		-33.84	151.01	16716
Grao de Murviedro	ES		39.64	-0.24	62368
Grapevine	US	Texas	32.93	-97.08	51404
Gravataí	BR		-29.94	-50.99	265074
Gravatá	BR		-8.20	-35.56	91887
Gravesend	US	New York	40.60	-73.97	112229
Gravesend	GB		51.44	0.37	54263
Grays	GB		51.48	0.33	89755
Grayslake	US	Illinois	42.34	-88.04	20915
Graz	AT		47.07	15.44	303270
Grazhdanka	RU		60.02	30.42	71128
Great Bend	US	Kansas	38.36	-98.76	15717
Great Falls	US	Montana	47.50	-111.30	59638
Great Falls	US	Virginia	39.00	-77.29	15427
Great Kills	US	New York	40.55	-74.15	22000
Great Malvern	GB		52.11	-2.33	36770
Great Sankey	GB		53.39	-2.64	43793
Great Wyrley	GB		52.66	-2.01	19193
Great Yarmouth	GB		52.61	1.73	63434
Greater Grand Crossing	US	Illinois	41.76	-87.61	32346
Greater Napanee	CA		44.25	-76.95	15892
Greater Noida	IN		28.50	77.54	293908
Greater Northdale	US	Florida	28.11	-82.53	22079
Greater Sudbury	CA		46.49	-80.99	166004
Greater Upper Marlboro	US	Maryland	38.83	-76.75	18720
Greeley	US	Colorado	40.42	-104.71	108795
Green	US	Ohio	40.95	-81.48	25898
Green Bay	US	Wisconsin	44.52	-88.02	105207
Green Haven	US	Maryland	39.14	-76.55	19326
Green Valley	US	Arizona	31.85	-110.99	21391
Greenacre	AU		-33.90	151.06	24361
Greenacres City	US	Florida	26.62	-80.13	32963
Greenbelt	US	Maryland	39.00	-76.88	24272
Greenburgh	US	New York	41.03	-73.84	86764
Greeneville	US	Tennessee	36.16	-82.83	15094
Greenfield	US	Wisconsin	42.96	-88.01	37349
Greenfield	US	Indiana	39.79	-85.77	21497
Greenfield	US	Massachusetts	42.59	-72.60	19753
Greenfield	US	California	36.32	-121.24	17184
Greenfield Park	CA		45.49	-73.46	16733
Greenford	GB		51.53	-0.36	38000
Greenock	GB		55.95	-4.76	41280
Greenpoint	US	New York	40.72	-73.95	34719
Greensboro	US	North Carolina	36.07	-79.79	285342
Greensborough	AU		-37.70	145.10	21070
Greenvale	AU		-37.63	144.87	21274
Greenville	US	North Carolina	35.61	-77.37	90597
Greenville	US	South Carolina	34.85	-82.39	64579
Greenville	US	Mississippi	33.41	-91.06	32156
Greenville	US	Texas	33.14	-96.11	26515
Greenwich	GB		51.48	-0.01	30578
Greenwood	US	Indiana	39.61	-86.11	55586
Greenwood	US	South Carolina	34.20	-82.16	23260
Greenwood	US	Mississippi	33.52	-90.18	15431
Greenwood Village	US	Colorado	39.62	-104.95	15663
Greer	US	South Carolina	34.94	-82.23	28365
Grenoble	FR		45.18	5.71	158552
Gresham	US	Oregon	45.50	-122.43	110553
Gresik	ID		-7.15	112.66	73629
Gretna	US	Louisiana	29.91	-90.05	17880
Grevenbroich	DE		51.09	6.58	64779
Greystanes	AU		-33.82	150.95	23511
Greystones	IE		53.14	-6.06	22009
Griffin	US	Georgia	33.25	-84.26	23211
Griffith	AU		-34.29	146.05	20569
Griffith	US	Indiana	41.53	-87.42	16378
Grimsby	GB		53.57	-0.08	86138
Grimsby	CA		43.20	-79.57	27314
Grogol	ID		-7.60	110.82	100613
Gronau	DE		52.21	7.02	50547
Groningen	NL		53.22	6.57	244807
Grosse Pointe Woods	US	Michigan	42.44	-82.91	15762
Grosseto	IT		42.76	11.11	60922
Grove City	US	Ohio	39.88	-83.09	39388
Groves	US	Texas	29.95	-93.92	15750
Grozny	RU		43.31	45.69	297137
Grudziądz	PL		53.48	18.75	92552
Grytviken	GS		-54.28	-36.51	2
Gràcia	ES		41.40	2.16	121502
Guacara	VE		10.23	-67.88	198883
Guadalajara	MX		20.68	-103.35	1385629
Guadalajara	ES		40.63	-3.16	93470
Guadalajara de Buga	CO		3.90	-76.30	114316
Guadalupe	MX		25.68	-100.26	673616
Guadalupe	MX		22.75	-102.52	170029
Guaianases	BR		-23.54	-46.41	109316
Gualeguaychú	AR		-33.01	-58.52	78676
Guamúchil	MX		25.46	-108.08	72500
Guanabacoa	CU		23.13	-82.30	112964
Guanajuato	MX		21.02	-101.26	72237
Guanambi	BR		-14.22	-42.78	87817
Guanare	VE		9.04	-69.73	112286
Guangshui	CN		31.62	114.00	154771
Guangyuan	CN		32.44	105.82	516424
Guangzhou	CN		23.12	113.25	16096724
Guang’an	CN		30.47	106.64	858159
Guanhu	CN		34.43	118.00	97705
Guankou	CN		28.16	113.63	1380000
Guanshan	CN		33.80	117.87	51086
Guantánamo	CU		20.14	-75.21	272801
Guanyin	CN		29.10	104.39	63606
Guanzhuang	CN		36.26	119.19	50826
Guapimirim	BR		-22.54	-42.98	54300
Guarabira	BR		-6.85	-35.49	57484
Guarapari	BR		-20.67	-40.50	124656
Guarapuava	BR		-25.39	-51.47	182093
Guaratinguetá	BR		-22.82	-45.19	118044
Guarenas	VE		10.47	-66.62	248588
Guarujá	BR		-23.99	-46.26	322750
Guarulhos	BR		-23.46	-46.53	1169577
Guará	BR		-15.81	-47.97	120641
Guasave	MX		25.57	-108.47	71196
Guasdualito	VE		7.24	-70.73	64608
Guatemala City	GT		14.64	-90.51	994938
Guatire	VE		10.47	-66.54	227666
Guaxupé	BR		-21.31	-46.71	50911
Guayaquil	EC		-2.20	-79.89	2723665
Guaynabo	PR		18.36	-66.11	81360
Guaíba	BR		-30.11	-51.33	92924
Gubat	PH		12.92	124.12	61095
Gubkin	RU		51.28	37.54	87000
Gucheng	CN		36.95	118.76	60149
Gucheng Chengguanzhen	CN		32.27	111.63	74038
Gucun	CN		31.35	121.39	240185
Gudivāda	IN		16.44	81.00	118167
Gudiyatham	IN		12.95	78.87	93973
Gueckedou	GN		8.57	-10.13	79140
Guelma	DZ		36.46	7.43	120004
Guelmim	MA		28.99	-10.06	129200
Guelph	CA		43.55	-80.26	143740
Guerara	DZ		32.79	4.50	58572
Guercif	MA		34.23	-3.35	99238
Guider	CM		9.93	13.95	81608
Guidonia Montecelio	IT		41.99	12.72	89165
Guigang	CN		23.12	109.59	1086327
Guiglo	CI		6.54	-7.49	68113
Guiguinto	PH		14.83	120.88	118173
Guildford	GB		51.24	-0.57	71873
Guildford	CA		49.19	-122.80	64985
Guilford	US	Connecticut	41.29	-72.68	22498
Guilin	CN		25.28	110.30	1572300
Guiping	CN		23.39	110.07	71066
Guiren	CN		33.67	118.19	57446
Guisborough	GB		54.53	-1.06	16979
Guiseley	GB		53.88	-1.71	21000
Guixi	CN		30.33	107.35	188980
Guiyang	CN		26.58	106.72	3037159
Gujangbagh	CN		37.11	79.93	408894
Gujar Khan	PK		33.25	73.30	69374
Gujranwala	PK		32.16	74.19	2511118
Gujrat	PK		32.57	74.08	574240
Gukovo	RU		48.05	39.93	66079
Gulariyā	NP		28.21	81.35	53107
Gulfport	US	Mississippi	30.37	-89.09	71856
Guli	CN		28.88	120.03	536000
Gulin	CN		28.04	105.81	116527
Guliston	UZ		40.50	68.78	90398
Gulu	UG		2.77	32.30	177400
Gumi	KR		36.11	128.34	404691
Gumlā	IN		23.04	84.54	51264
Gummersbach	DE		51.03	7.56	53131
Guna	IN		24.65	77.31	180935
Gunan	CN		29.02	106.65	208010
Gundupālaiyam	IN		11.94	79.80	300104
Gunpo	KR		37.37	126.95	286485
Gunsan	KR		35.98	126.71	264656
Guntakal	IN		15.17	77.36	126270
Guntur	IN		16.30	80.46	670073
Gunungsitoli	ID		1.29	97.61	136707
Gununo	ET		6.92	37.65	84510
Guozhen	CN		34.37	107.36	85415
Gurdaspur	IN		32.04	75.40	77928
Guri-si	KR		37.60	127.14	195236
Gurlan	UZ		41.84	60.39	50900
Gurnee	US	Illinois	42.37	-87.90	31056
Gurugram	IN		28.46	77.03	886519
Gurupi	BR		-11.73	-49.07	89574
Gurúè	MZ		-15.47	36.98	168971
Gusau	NG		12.17	6.66	226857
Gushikawa	JP		26.36	127.87	65251
Gushu	CN		31.56	118.48	60335
Gusong	CN		28.31	105.24	87882
Gustavia	BL		17.90	-62.85	5988
Gustavo Adolfo Madero	MX		19.49	-99.11	1185772
Gus’-Khrustal’nyy	RU		55.61	40.65	62746
Guwahati	IN		26.18	91.75	962334
Guyong	PH		14.84	120.98	155391
Guyuan	CN		36.01	106.28	411854
Guédiawaye	SN		14.77	-17.40	329659
Gwa	MM		17.59	94.58	66015
Gwadar	PK		25.12	62.33	70852
Gwalior	IN		26.23	78.17	1054420
Gwangju	KR		35.15	126.92	1401235
Gwangju	KR		37.41	127.26	81780
Gwangmyeong	KR		37.48	126.87	357545
Gwangyang	KR		34.94	127.70	154266
Gweru	ZW		-19.45	29.82	158200
Gwynn Oak	US	Maryland	39.33	-76.69	47092
Gyeongju	KR		35.84	129.21	245365
Gyeongsan-si	KR		35.82	128.74	266951
Gympie	AU		-26.19	152.66	22424
Gyumri	AM		40.79	43.85	114667
Gyānpur	IN		25.33	82.47	200000
Gyōda	JP		36.14	139.46	86343
Győr	HU		47.68	17.64	129301
Gävle	SE		60.67	17.14	74884
Gò Công	VN		10.37	106.67	97709
Gò Vấp	VN		10.82	106.68	110850
Gómez Palacio	MX		25.57	-103.50	257352
Gölbaşı	TR		39.79	32.81	165201
Gölcük	TR		40.72	29.82	56189
Göppingen	DE		48.70	9.65	58040
Görlitz	DE		51.16	14.99	57751
Göttingen	DE		51.53	9.93	122149
Güigüe	VE		10.08	-67.78	80627
Güines	CU		22.84	-82.03	68935
Güira de Melena	CU		22.80	-82.51	69879
Güngören Merter	TR		41.01	28.89	50000
Gütersloh	DE		51.91	8.38	96180
Gāndhīdhām	IN		23.08	70.13	247992
Głogów	PL		51.66	16.08	65400
Gūdūr	IN		14.15	79.85	74851
H Street NE	US	District of Columbia	38.90	-77.00	21480
Ha'il	SA		27.52	41.69	605930
Haabersti	EE		59.42	24.65	51423
Haarlem	NL		52.38	4.64	162543
Habboûch	LB		33.41	35.48	98433
Habiganj	BD		24.38	91.41	88760
Habikino	JP		34.55	135.59	109479
Hachinohe	JP		40.50	141.50	239046
Hachiōji	JP		35.66	139.32	579355
Hacienda Heights	US	California	33.99	-117.97	54038
Hacienda Santa Fe	MX		20.52	-103.38	86935
Hackensack	US	New Jersey	40.89	-74.04	44834
Hadano	JP		35.37	139.22	163787
Haddington	US	Pennsylvania	39.97	-75.24	20073
Hadejia	NG		12.45	10.04	110753
Hadera	IL		32.44	34.90	97335
Hadleigh	GB		51.55	0.61	18300
Hadley Wood	GB		51.67	-0.17	21639
Haeju	KP		38.04	125.71	222396
Hafar Al-Batin	SA		28.43	45.97	271642
Hafizabad	PK		32.07	73.69	318621
Hagen	DE		51.36	7.47	198972
Hagere Maryam	ET		5.63	38.24	57700
Hagerstown	US	Maryland	39.64	-77.72	40432
Hagonoy	PH		14.83	120.73	123531
Hai Bà Trưng	VN		21.01	105.85	303586
Haicheng	CN		40.85	122.75	191651
Haifa	IL		32.81	35.00	285316
Haikou	CN		20.03	110.35	2873358
Haikou	CN		24.78	102.58	112644
Hailar	CN		49.20	119.70	211066
Hailin	CN		44.57	129.39	144443
Hailsham	GB		50.86	0.26	23411
Hailun	CN		47.45	126.92	109881
Haimen	CN		23.19	116.61	125427
Haines City	US	Florida	28.11	-81.62	22807
Haining	CN		30.54	120.69	70171
Haiphong	VN		20.86	106.68	2625200
Haizhou	CN		34.58	119.13	59098
Hajiawa	IQ		36.24	44.79	80000
Hakkâri	TR		37.57	43.74	77699
Hakodate	JP		41.78	140.74	275730
Hala	PK		25.81	68.42	71094
Halabja	IQ		35.18	45.99	57333
Haldia	IN		22.06	88.11	170695
Haldwani	IN		29.22	79.53	139497
Hale	GB		53.38	-2.33	16715
Hale	GB		51.23	-0.79	15657
Halesowen	GB		52.45	-2.05	60097
Halewood	GB		53.36	-2.83	20430
Halifax	CA		44.64	-63.58	471559
Halifax	GB		53.72	-1.85	82624
Halifax South End	CA		44.63	-63.58	19922
Halifax West End	CA		44.65	-63.62	22664
Hallandale Beach	US	Florida	25.98	-80.15	39488
Halle (Saale)	DE		51.48	11.98	237865
Halmstad	SE		56.67	12.86	70480
Haltom City	US	Texas	32.80	-97.27	44206
Halton Hills	CA		43.64	-79.93	62951
Ham Lake	US	Minnesota	45.25	-93.25	16062
Hamada	JP		34.88	132.08	57142
Hamadān	IR		34.80	48.51	528256
Hamakita	JP		34.80	137.78	86502
Hamamatsu	JP		34.70	137.73	791707
Hamburg	DE		53.55	9.99	1973896
Hamburg-Mitte	DE		53.55	10.02	301231
Hamburg-Nord	DE		53.59	9.98	315514
Hamden	US	Connecticut	41.40	-72.90	59847
Hameln	DE		52.10	9.36	58666
Hamhŭng	KP		39.92	127.54	559056
Hami	CN		42.83	93.51	246373
Hamilton	CA		43.25	-79.85	569353
Hamilton	NZ		-37.78	175.28	192100
Hamilton	US	Ohio	39.40	-84.56	62407
Hamilton	GB		55.77	-4.03	54480
Hamilton	BM		32.29	-64.78	902
Hamilton East	NZ		-37.79	175.29	15300
Hamm	DE		51.68	7.82	178967
Hamma Bouziane	DZ		36.41	6.60	83603
Hammamet	TN		36.40	10.62	106326
Hammanskraal	ZA		-25.41	28.29	112950
Hammond	US	Indiana	41.58	-87.50	77614
Hammond	US	Louisiana	30.50	-90.46	20480
Hampton	US	Virginia	37.03	-76.35	137148
Hampton	GB		51.41	-0.37	20000
Hampton Park	AU		-38.03	145.25	26082
Hamtramck	US	Michigan	42.39	-83.05	22002
Hamura	JP		35.76	139.32	54622
Hanahan	US	South Carolina	32.92	-80.02	17997
Hanam	KR		37.54	127.21	254415
Hanamaki	JP		39.38	141.12	94691
Hanau am Main	DE		50.13	8.91	88648
Hancheng	CN		35.46	110.43	58049
Hanchuan	CN		30.65	113.77	87737
Handa	JP		34.88	136.93	117884
Handan	CN		36.61	114.49	1358318
Handeni	TZ		-5.43	38.02	108968
Haney	CA		49.22	-122.60	21041
Hanfeng	CN		31.17	108.40	196528
Hanford	US	California	36.33	-119.65	55659
Hangu	CN		39.25	117.79	208369
Hangzhou	CN		30.29	120.16	9236032
Haninge	SE		59.17	18.14	74968
Hanjia	CN		29.30	108.16	108430
Hannan	JP		34.33	135.25	52350
Hannibal	US	Missouri	39.71	-91.36	17839
Hannover	DE		52.37	9.73	515140
Hannō	JP		35.85	139.32	80361
Hanoi	VN		21.02	105.84	8053663
Hanover	US	Maryland	39.19	-76.72	38088
Hanover	US	Massachusetts	42.11	-70.81	16906
Hanover	US	Pennsylvania	39.80	-76.98	15496
Hanover Park	US	Illinois	42.00	-88.15	38333
Hanting	CN		36.77	119.21	90637
Hanumāngarh	IN		29.58	74.33	155687
Hanworth	GB		51.43	-0.38	23563
Hanyin Chengguanzhen	CN		32.89	108.50	66926
Hanyuan	CN		32.83	106.25	50440
Hanyū	JP		36.17	139.53	58686
Hanzhong	CN		33.08	107.02	1006557
Happy Valley	US	Oregon	45.45	-122.53	18493
Harar	ET		9.31	42.12	157000
Harare	ZW		-17.83	31.05	1542813
Harbin	CN		45.75	126.65	5242897
Harburg	DE		53.46	9.98	169221
Harda	IN		22.34	77.10	74268
Hardenberg	NL		52.58	6.62	57909
Hardoī	IN		27.39	80.13	122635
Hargeysa	SO		9.56	44.06	477876
Haridwar	IN		29.95	78.16	186079
Harihar	IN		14.51	75.81	83219
Haripur	PK		34.00	72.93	56977
Harker Heights	US	Texas	31.08	-97.66	29142
Harlem	US	New York	40.81	-73.95	116345
Harlesden	GB		51.54	-0.25	17162
Harlingen	US	Texas	26.19	-97.70	65774
Harlow	GB		51.78	0.11	93300
Harpenden	GB		51.82	-0.36	30674
Harringay	GB		51.58	-0.10	16500
Harrisburg	US	Pennsylvania	40.27	-76.88	50183
Harrison	US	New York	40.97	-73.71	28348
Harrison	US	New Jersey	40.75	-74.16	15474
Harrisonburg	US	Virginia	38.45	-78.87	52538
Harrogate	GB		53.99	-1.54	89060
Harrow	GB		51.58	-0.33	149246
Harsīn	IR		34.27	47.59	57647
Hartford	US	Connecticut	41.76	-72.69	121054
Hartlepool	GB		54.69	-1.21	88855
Hartley	GB		51.39	0.30	16302
Hartranft	US	Pennsylvania	39.98	-75.15	19748
Harunabad	PK		29.61	73.14	149679
Harvey	US	Illinois	41.61	-87.65	25194
Harvey	US	Louisiana	29.90	-90.08	20348
Harwich	GB		51.94	1.28	20723
Hasanpur	IN		28.72	78.28	57481
Hashima	JP		35.33	136.68	67909
Hashimoto	JP		34.32	135.62	61063
Hashtgerd	IR		35.96	50.68	55640
Hashtsāl	IN		28.63	77.06	176877
Hasilpur	PK		29.69	72.55	168146
Haskovo	BG		41.93	25.56	64564
Haslemere	GB		51.09	-0.71	17279
Haslett	US	Michigan	42.75	-84.40	19220
Haslingden	GB		53.70	-2.32	15204
Hassan	IN		13.01	76.10	155006
Hasselt	BE		50.93	5.34	77651
Hassi Bahbah	DZ		35.07	3.03	77000
Hastings	GB		50.86	0.58	92855
Hastings	NZ		-39.64	176.85	88300
Hastings	US	Nebraska	40.59	-98.39	24924
Hastings	US	Minnesota	44.74	-92.85	22554
Hastings-Sunrise	CA		49.28	-123.03	34575
Hasuda	JP		35.97	139.65	61540
Hat Yai	TH		7.01	100.48	191696
Hatfield	GB		51.76	-0.22	41265
Hatogaya-honchō	JP		35.83	139.74	53062
Hatsukaichi	JP		34.35	132.33	114173
Hattiesburg	US	Mississippi	31.33	-89.29	46805
Hattingen	DE		51.40	7.19	56866
Hauppauge	US	New York	40.83	-73.20	20882
Havana	CU		23.13	-82.38	2163824
Havant	GB		50.86	-0.99	45574
Haveli Lakha	PK		30.45	73.69	122389
Havelock	US	North Carolina	34.88	-76.90	20364
Haverhill	US	Massachusetts	42.78	-71.08	62765
Haverhill	GB		52.08	0.44	27041
Havertown	US	Pennsylvania	39.98	-75.31	50430
Havířov	CZ		49.78	18.44	82768
Hawai‘i Kai	US	Hawaii	21.30	-157.70	30620
Hawarden	GB		53.18	-3.03	25513
Hawr al ‘Anz	AE		25.28	55.34	84661
Hawthorn	AU		-37.82	145.04	22322
Hawthorn South	AU		-37.83	145.04	21177
Hawthorne	US	California	33.92	-118.35	88451
Hawthorne	US	New Jersey	40.95	-74.15	19074
Haydock	GB		53.47	-2.68	17333
Hayes	GB		51.52	-0.42	93928
Hayes	GB		51.38	0.02	15908
Hayesville	US	Oregon	44.99	-122.98	19936
Hayling Island	GB		50.78	-0.97	16887
Hays	US	Kansas	38.88	-99.33	21092
Hayward	US	California	37.67	-122.08	158289
Haywards Heath	GB		51.00	-0.10	33845
Hazel Dell	US	Washington	45.67	-122.66	19435
Hazel Grove	GB		53.38	-2.12	20170
Hazel Park	US	Michigan	42.46	-83.10	16597
Hazelwood	US	Missouri	38.77	-90.37	25661
Hazleton	US	Pennsylvania	40.96	-75.97	24825
Hazāribāgh	IN		23.99	85.36	153595
Heanor	GB		53.01	-1.35	23122
Heavitree	GB		50.72	-3.50	22000
Hebburn	GB		54.97	-1.52	21345
Hebi	CN		35.73	114.29	634721
Hebron	PS		31.53	35.09	160470
Hechi	CN		24.69	108.08	330131
Hechuan	CN		29.99	106.26	377213
Heckmondwike	GB		53.71	-1.68	18149
Hecun	CN		36.53	114.11	83009
Hede	CN		33.77	120.26	89107
Hedge End	GB		50.91	-1.30	17978
Hedong	CN		23.92	115.78	101825
Heerlen	NL		50.88	5.98	93084
Hefei	CN		31.86	117.28	5050000
Hegang	CN		47.35	130.29	743307
Heguan	CN		36.89	118.57	73470
Heho	MM		20.72	96.82	93041
Heidelberg	DE		49.41	8.69	143345
Heidelberg	ZA		-26.50	28.36	85858
Heidenheim an der Brenz	DE		48.68	10.15	50067
Heihe	CN		50.24	127.49	223832
Heilbronn	DE		49.14	9.22	120733
Heishan	CN		41.69	122.11	68603
Hejiang	CN		28.81	105.83	137437
Hekinan	JP		34.88	136.98	72458
Helena	US	Montana	46.59	-112.04	32091
Helena	US	Alabama	33.30	-86.84	18264
Helensvale	AU		-27.92	153.33	16839
Hell's Kitchen	US	New York	40.76	-73.99	45884
Hell-Ville	MG		-13.40	48.27	53219
Hellersdorf	DE		52.53	13.61	84103
Helmond	NL		51.48	5.66	74740
Helong	CN		42.54	129.00	85756
Helsingborg	SE		56.05	12.69	104250
Helsinki	FI		60.17	24.94	658864
Hemel Hempstead	GB		51.75	-0.45	95961
Hemet	US	California	33.75	-116.97	83861
Hempstead	US	New York	40.71	-73.62	55547
Hendala	LK		6.99	79.88	56978
Henderson	US	Nevada	36.04	-114.98	285667
Henderson	US	Kentucky	37.84	-87.59	28890
Henderson	NZ		-36.88	174.62	18770
Henderson	US	North Carolina	36.33	-78.40	15271
Hendersonville	US	Tennessee	36.30	-86.62	56018
Hengbei	CN		23.88	115.73	78575
Hengelo	NL		52.27	6.79	82311
Hengshan	CN		45.21	130.90	164844
Hengshui	CN		37.74	115.68	522147
Hengyang	CN		26.89	112.62	1075516
Henrietta	US	New York	43.06	-77.61	42581
Henry Farm	CA		43.77	-79.35	15723
Hepingjie	CN		42.06	126.92	65298
Hepo	CN		23.43	115.83	131238
Hepu	CN		21.66	109.20	192813
Hercules	US	California	38.02	-122.29	25314
Hereford	GB		52.06	-2.71	60415
Hereford	US	Texas	34.82	-102.40	15021
Herford	DE		52.11	8.67	64879
Hermanus	ZA		-34.42	19.23	56139
Hermiston	US	Oregon	45.84	-119.29	17201
Hermitage	US	Tennessee	36.20	-86.62	37814
Hermitage	US	Pennsylvania	41.23	-80.45	16028
Hermosa Beach	US	California	33.86	-118.40	19860
Hermosillo	MX		29.09	-110.97	812229
Hernals	AT		48.23	16.31	57546
Hernando	US	Mississippi	34.82	-89.99	15503
Herndon	US	Virginia	38.97	-77.39	24568
Herne	DE		51.54	7.23	172108
Herne Bay	GB		51.37	1.13	24875
Herning	DK		56.14	8.98	50565
Heroica Caborca	MX		30.72	-112.16	59922
Heroica Ciudad de Juchitán de Zaragoza	MX		16.43	-95.02	88280
Heroica Guaymas	MX		27.92	-110.90	117253
Heroica Matamoros	MX		25.88	-97.50	510739
Herriman	US	Utah	40.51	-112.03	30835
Herten	DE		51.60	7.14	65306
Hertford	GB		51.80	-0.08	25847
Hervey Bay	AU		-25.29	152.77	52230
Herzliya	IL		32.17	34.83	97470
Heróica Zitácuaro	MX		19.44	-100.36	84307
Herāt	AF		34.35	62.20	574300
Heshan	CN		28.57	112.35	1249807
Hespeler	CA		43.43	-80.32	18445
Hesperia	US	California	34.43	-117.30	93295
Heston	GB		51.48	-0.38	37045
Heswall	GB		53.33	-3.10	29075
Hetauda	NP		27.43	85.03	195951
Heysham	GB		54.04	-2.89	17016
Heyuan	CN		23.73	114.68	463907
Heywood	GB		53.59	-2.22	28024
Heze	CN		35.24	115.47	1346717
Hezhou	CN		24.40	111.57	1005490
Hezuo	CN		34.99	102.91	59148
Hialeah	US	Florida	25.86	-80.28	237069
Hialeah Gardens	US	Florida	25.87	-80.32	23926
Hibbing	US	Minnesota	47.43	-92.94	16204
Hickory	US	North Carolina	35.73	-81.34	40374
Hicksville	US	New York	40.77	-73.53	41547
Hidaka	JP		35.92	139.36	55294
Hidalgo del Parral	MX		26.93	-105.67	104836
Hietzing	AT		48.19	16.30	54265
Higashi-Matsuyama	JP		36.03	139.42	91791
Higashihiroshima	JP		34.41	132.74	196608
Higashikurume	JP		35.75	139.51	117020
Higashimurayama	JP		35.75	139.47	151815
Higashiosaka	JP		34.67	135.58	493940
Higashiyamato	JP		35.76	139.45	83901
High Blantyre	GB		55.78	-4.10	16739
High Park North	CA		43.66	-79.47	22162
High Park-Swansea	CA		43.65	-79.47	23925
High Peak	GB		53.37	-1.85	92666
High Point	US	North Carolina	35.96	-80.01	110268
High Wycombe	GB		51.63	-0.75	133204
Highbury	GB		51.55	-0.10	26664
Highland	US	California	34.13	-117.21	54854
Highland	US	Indiana	41.55	-87.45	22936
Highland	US	Utah	40.43	-111.79	17989
Highland Park	US	Illinois	42.18	-87.80	29743
Highland Springs	US	Virginia	37.55	-77.33	15711
Highland Village	US	Texas	33.09	-97.05	16149
Highlands Ranch	US	Colorado	39.55	-104.97	96713
Highton	AU		-38.17	144.31	18388
Highview	US	Kentucky	38.14	-85.62	15167
Hihyā	EG		30.67	31.59	74823
Hikari	JP		33.95	131.95	51040
Hikone	JP		35.25	136.25	113647
Hilden	DE		51.17	6.93	56565
Hildesheim	DE		52.15	9.95	103052
Hillcrest Heights	US	Maryland	38.83	-76.96	16469
Hillcrest Village	CA		43.80	-79.35	16934
Hilliard	US	Ohio	40.03	-83.16	33649
Hillsboro	US	Oregon	45.52	-122.99	102347
Hillsborough	US	New Jersey	40.48	-74.63	38303
Hillside	US	New York	40.71	-73.79	24808
Hillside	US	New Jersey	40.70	-74.23	22155
Hillside	AU		-37.69	144.74	17331
Hilo	US	Hawaii	19.73	-155.09	43263
Hilsa	IN		25.32	85.28	51052
Hilton Head	US	South Carolina	32.22	-80.75	37099
Hilton Head Island	US	South Carolina	32.19	-80.74	40512
Hilversum	NL		52.22	5.18	83640
Himamaylan	PH		10.10	122.87	117286
Himatnagar	IN		23.60	72.97	81137
Himeji	JP		34.82	134.70	530495
Himimachi	JP		36.86	136.99	54510
Hinckley	GB		52.54	-1.38	50712
Hindaun	IN		26.73	77.04	105452
Hindley	GB		53.53	-2.58	25001
Hindupur	IN		13.83	77.49	151677
Hinesville	US	Georgia	31.85	-81.60	33398
Hinganghāt	IN		20.55	78.84	101805
Hingoli	IN		19.71	77.14	85103
Hino	JP		35.67	139.40	190435
Hinsdale	US	Illinois	41.80	-87.94	17628
Hinthada	MM		17.65	95.46	134947
Hirakata	JP		34.81	135.65	406331
Hiratsuka	JP		35.33	139.34	258422
Hiriyūr	IN		13.94	76.62	56416
Hirnytskyi	UA		48.02	37.97	107216
Hirosaki	JP		40.59	140.47	168739
Hiroshima	JP		34.40	132.45	1200754
Hisar	IN		29.15	75.72	307024
Hita	JP		33.32	130.94	64874
Hitachi	JP		36.60	140.65	174508
Hitachi-Naka	JP		36.40	140.53	156581
Hitchin	GB		51.95	-0.28	35220
Hlaingthaya	MM		16.85	96.07	687867
Ho	GH		6.60	0.47	130701
Ho Chi Minh City	VN		10.82	106.63	14002598
Hobart	AU		-42.88	147.33	254930
Hobart	US	Indiana	41.53	-87.26	28404
Hobbs	US	New Mexico	32.70	-103.14	38416
Hoboken	US	New Jersey	40.74	-74.03	53635
Hod HaSharon	IL		32.16	34.89	63175
Hodal	IN		27.89	77.37	50143
Hoddesdon	GB		51.76	-0.01	35174
Hoffman Estates	US	Illinois	42.04	-88.08	52138
Hohhot	CN		40.81	111.65	2350000
Hohoe	GH		7.15	0.47	92076
Hoima	UG		1.43	31.35	122700
Hoji ya Henda	AO		-8.81	13.29	642050
Holbrook	US	New York	40.81	-73.08	27195
Holden	US	Massachusetts	42.35	-71.86	17016
Holguín	CU		20.89	-76.26	319102
Holiday	US	Florida	28.19	-82.74	22403
Holladay	US	Utah	40.67	-111.82	30864
Holland	US	Michigan	42.79	-86.11	33742
Hollis	US	New York	40.71	-73.77	20269
Hollister	US	California	36.85	-121.40	37462
Holloway	GB		51.55	-0.12	41329
Holly Springs	US	North Carolina	35.65	-78.83	31377
Hollywood	US	California	34.10	-118.33	167664
Hollywood	US	Florida	26.01	-80.15	149728
Holmesburg	US	Pennsylvania	40.04	-75.03	28046
Holosiyiv	UA		50.34	30.55	62200
Holt	US	Michigan	42.64	-84.52	23973
Holtsville	US	New York	40.82	-73.05	19714
Holyoke	US	Massachusetts	42.20	-72.62	40684
Homer Glen	US	Illinois	41.60	-87.94	24395
Homestead	US	Florida	25.47	-80.48	80737
Homewood	US	Alabama	33.47	-86.80	25708
Homewood	US	Illinois	41.56	-87.67	19373
Homs	SY		34.72	36.73	775404
Homyel'	BY		52.43	30.98	501193
Honchō	JP		35.70	139.99	644668
Hong Kong	HK		22.28	114.17	7396076
Hong Kong Island	HK		22.26	114.18	1195529
Hongch’ŏn	KR		37.69	127.89	75251
Honggang	CN		46.40	124.88	147977
Honghe	CN		36.40	118.92	88458
Hongjiang	CN		27.11	110.00	59199
Hongkou	CN		31.25	121.49	687500
Hongqiao	CN		26.77	112.11	58287
Hongseong	KR		36.60	126.67	89174
Hongwŏn	KP		40.03	127.96	70923
Honiara	SB		-9.43	159.95	56298
Honjō	JP		36.24	139.19	78569
Honmachi	JP		32.50	130.60	123067
Honolulu	US	Hawaii	21.31	-157.86	350964
Hoofddorp	NL		52.30	4.69	132734
Hook	GB		51.37	-0.31	18973
Hoorn	NL		52.64	5.06	68852
Hoover	US	Alabama	33.41	-86.81	84848
Hopatcong Hills	US	New Jersey	40.94	-74.67	16267
Hope Mills	US	North Carolina	34.97	-78.95	16163
Hopewell	US	Virginia	37.30	-77.29	22378
Hopkins	US	Minnesota	44.92	-93.46	17591
Hopkinsville	US	Kentucky	36.87	-87.49	32205
Hoppers Crossing	AU		-37.88	144.70	37216
Horad Zhodzina	BY		54.10	28.33	62983
Horizon City	US	Texas	31.69	-106.21	19288
Horizonte	BR		-4.10	-38.49	70983
Horley	GB		51.17	-0.16	21232
Horlivka	UA		48.30	38.02	239828
Horn Lake	US	Mississippi	34.96	-90.03	26915
Hornchurch	GB		51.56	0.22	25470
Hornsby	AU		-33.70	151.10	22462
Horsens	DK		55.86	9.85	61074
Horsforth	GB		53.84	-1.64	19350
Horsham	GB		51.06	-0.33	51472
Horsham	AU		-36.71	142.20	16985
Horta-Guinardó	ES		41.42	2.17	168092
Hortaleza	ES		40.47	-3.64	161661
Hortolândia	BR		-22.86	-47.22	234259
Horwich	GB		53.60	-2.55	18696
Hosapete	IN		15.27	76.39	206167
Hosa’ina	ET		7.55	37.85	188200
Hoshiārpur	IN		31.54	75.91	168653
Hoskote	IN		13.07	77.80	56980
Hosūr	IN		12.74	77.83	229528
Hot Springs	US	Arkansas	34.50	-93.06	35635
Hougang New Town	SG		1.36	103.89	227560
Hough	US	Ohio	41.51	-81.64	16359
Houghton-Le-Spring	GB		54.84	-1.46	36746
Houma	US	Louisiana	29.60	-90.72	34287
Houmt Souk	TN		33.88	10.86	89228
Houndé	BF		11.50	-3.52	87151
Hounslow	GB		51.47	-0.36	66292
Houston	US	Texas	29.76	-95.36	2314157
Houzhen	CN		36.99	118.97	96737
Hove	GB		50.83	-0.17	75174
Howard	US	Wisconsin	44.54	-88.09	19250
Howard Beach	US	New York	40.66	-73.84	26148
Howrah	IN		22.58	88.32	1027672
Hoyland Nether	GB		53.50	-1.45	15842
Hoàn Kiếm	VN		21.03	105.85	135618
Hoàng Mai	VN		19.27	105.72	113360
Hpa-An	MM		16.89	97.63	50000
Hpākān	MM		25.61	96.31	60123
Hradec Králové	CZ		50.21	15.83	90596
Hrodna	BY		53.68	23.83	363718
Hruzkyi	UA		48.07	37.94	52265
Hsinchu	TW		24.80	120.97	453536
Hua Hin	TH		12.57	99.96	126355
Huacheng	CN		24.07	115.61	101165
Huacho	PE		-11.12	-77.61	54545
Huadian	CN		42.97	126.74	139047
Huai Khwang	TH		13.78	100.58	78175
Huai'an	CN		33.59	119.02	2494013
Huaibei	CN		33.97	116.79	1113321
Huaicheng	CN		23.92	112.18	89294
Huaidian	CN		33.43	115.03	89978
Huaihua	CN		27.56	110.00	552622
Huainan	CN		32.63	117.00	1666826
Huaiyang	CN		37.76	114.52	81861
Huaiyuan Chengguanzhen	CN		32.96	117.17	65530
Huajing	CN		31.12	121.45	67415
Hualien City	TW		23.98	121.60	99458
Hualong	CN		36.95	118.59	52660
Hualpén	CL		-36.79	-73.10	86639
Huamak	TH		13.76	100.65	67798
Huamantla	MX		19.31	-97.93	51996
Huambo	AO		-12.78	15.74	595304
Huanan	CN		46.24	130.55	66087
Huancayo	PE		-12.07	-75.21	456250
Huangchuan	CN		32.14	115.04	72663
Huanggang	CN		30.45	114.87	366769
Huanggang	CN		23.68	117.00	225956
Huanghua	CN		35.89	119.46	65646
Huanglou	CN		36.65	118.61	80055
Huangmei	CN		30.19	116.02	77633
Huangnihe	CN		43.56	128.02	54959
Huangpi	CN		30.88	114.38	57554
Huangpu	CN		31.24	121.48	504700
Huangshan	CN		29.71	118.31	460786
Huangshi	CN		30.25	115.05	688090
Huangzhou	CN		30.45	114.80	122563
Huankou	CN		34.87	116.67	77758
Huanren	CN		41.26	125.37	66147
Huaral	PE		-11.49	-77.21	62174
Huaraz	PE		-9.53	-77.53	118836
Huashan	CN		34.63	116.74	71281
Huauchinango	MX		20.17	-98.05	56206
Huayin	CN		34.57	110.07	242488
Huayuan	CN		28.29	117.21	73732
Huazhou	CN		21.63	110.58	91701
Hub	PK		25.03	66.89	195661
Hubballi	IN		15.35	75.13	943788
Huber Heights	US	Ohio	39.84	-84.12	38176
Hucknall	GB		53.03	-1.20	29728
Huddersfield	GB		53.65	-1.78	149017
Huddinge	SE		59.24	17.98	90182
Hudson	US	Ohio	41.24	-81.44	22437
Huehuetenango	GT		15.32	-91.47	79426
Huelva	ES		37.27	-6.94	144258
Huesca	ES		42.14	-0.41	53956
Hueytown	US	Alabama	33.45	-87.00	15710
Hugli	IN		22.91	88.40	177005
Huguo	CN		28.59	105.37	54795
Huicheng	CN		23.04	116.29	125919
Huicheng	CN		29.87	118.43	74349
Huilong	CN		31.81	121.66	74818
Huinan	CN		42.62	126.26	66315
Huinong	CN		39.23	106.77	136570
Huiqu	CN		36.27	119.05	59323
Huixing	CN		29.68	106.61	186972
Huixquilucan	MX		19.36	-99.35	124846
Huizhou	CN		23.11	114.42	2900113
Hujra Shah Muqim	PK		30.74	73.82	76462
Hulan	CN		45.89	126.58	109104
Hulan Ergi	CN		47.20	123.63	265344
Hull	CA		45.43	-75.71	63702
Hulu Langat	MY		3.11	101.81	55251
Huludao	CN		40.75	120.84	944495
Hulunbuir	CN		49.21	119.76	349400
Humaitá	BR		-7.52	-63.03	62312
Humbermede	CA		43.75	-79.54	15545
Humberstone	GB		52.65	-1.09	18854
Humble	US	Texas	30.00	-95.26	15665
Humen	CN		22.82	113.67	191891
Hunchun	CN		42.87	130.36	77028
Hunedoara	RO		45.75	22.90	69136
Hunsūr	IN		12.30	76.29	50865
Hunt Valley	US	Maryland	39.50	-76.64	23915
Huntersville	US	North Carolina	35.41	-80.84	52704
Hunting Park	US	Pennsylvania	40.02	-75.14	17682
Huntingdon	GB		52.33	-0.19	23937
Huntington	US	West Virginia	38.42	-82.45	48638
Huntington	US	New York	40.87	-73.43	18046
Huntington	US	Indiana	40.88	-85.50	17095
Huntington Beach	US	California	33.66	-118.00	201899
Huntington Park	US	California	33.98	-118.23	59430
Huntington Station	US	New York	40.85	-73.41	33029
Huntley	US	Illinois	42.17	-88.43	26005
Hunts Cross	GB		53.36	-2.87	15740
Hunts Point	US	New York	40.81	-73.88	27204
Huntsville	US	Alabama	34.73	-86.59	215006
Huntsville	US	Texas	30.72	-95.55	40938
Huntsville	CA		45.33	-79.22	19816
Huocheng	CN		44.05	80.87	360000
Huoqiu Chengguanzhen	CN		32.35	116.29	61904
Hurghada	EG		27.26	33.81	207132
Hurlingham	AR		-34.59	-58.63	60000
Hurricane	US	Utah	37.18	-113.29	15501
Hurst	US	Texas	32.82	-97.17	39016
Hurstville	AU		-33.97	151.10	29744
Hushitai	CN		41.94	123.50	61979
Hutang	CN		31.53	119.49	56370
Hutchinson	US	Kansas	38.06	-97.93	41569
Hutto	US	Texas	30.54	-97.55	22722
Huyton	GB		53.41	-2.84	54738
Huyện Lâm Hà	VN		11.82	108.21	144707
Huzhou	CN		30.87	120.09	1015937
Huánuco	PE		-9.93	-76.24	196627
Huế	VN		16.46	107.60	1380000
Hvidovre	DK		55.64	12.48	53527
Hwadae	KP		40.84	129.50	67677
Hwado	KR		37.65	127.31	106358
Hwaseong-si	KR		37.21	126.82	640890
Hwasun	KR		35.06	126.99	59914
Hwasŏng	KP		41.26	129.49	99557
Hwawŏn	KR		35.80	128.50	64718
Hyattsville	US	Maryland	38.96	-76.95	18501
Hybla Valley	US	Virginia	38.75	-77.08	15801
Hyde	GB		53.45	-2.08	35895
Hyde Park	US	Massachusetts	42.26	-71.12	31845
Hyde Park	US	Illinois	41.79	-87.59	26893
Hyderabad	IN		17.38	78.46	6993262
Hyderabad	PK		25.40	68.38	1921275
Hyesan	KP		41.40	128.18	192680
Hyesan-dong	KP		41.40	128.19	97794
Hyosha	CD		0.70	29.52	74502
Hythe	GB		50.86	-1.40	20526
Hyères	FR		43.12	6.13	50487
Hyūga	JP		32.42	131.64	60037
Hà Giang	VN		22.82	104.98	55559
Hà Tiên	VN		10.38	104.49	100560
Hà Tĩnh	VN		18.34	105.91	266321
Hà Đông	VN		20.97	105.78	50877
Hämeenlinna	FI		61.00	24.46	68473
Hòa Bình	VN		20.82	105.34	105260
Hòa Cường	VN		16.04	108.18	119363
Hòa Thành	VN		11.29	106.13	147666
Hürth	DE		50.87	6.87	54678
Hābra	IN		22.84	88.66	139297
Hāgere Hiywet	ET		8.98	37.85	99900
Hājīpur	IN		25.69	85.21	147688
Hālol	IN		22.50	73.47	64265
Hālīsahar	IN		22.93	88.42	128172
Hānsi	IN		29.10	75.96	86770
Hāpur	IN		28.73	77.78	242920
Hāthazāri	BD		22.51	91.81	498179
Hāthras	IN		27.60	78.05	126882
Hāveri	IN		14.79	75.40	67102
Hōfu	JP		34.05	131.57	116925
Hŭngnam	KP		39.84	127.63	346082
Hưng Yên	VN		20.65	106.05	118646
Hương Thủy	VN		16.42	107.64	95299
Hương Trà	VN		16.53	107.48	72677
H̱olon	IL		32.01	34.78	196282
Hạ Long	VN		20.95	107.07	270054
Hải Châu	VN		15.92	108.13	131427
Hải Dương	VN		20.94	106.33	241373
Hồng Ngự	VN		10.80	105.35	101155
Iaşi	RO		47.17	27.60	378954
Ibadan	NG		7.38	3.91	3649000
Ibagué	CO		4.44	-75.20	529635
Ibanda	UG		-0.13	30.50	117700
Ibaraki	JP		34.82	135.57	287730
Ibarra	EC		0.35	-78.12	221149
Ibb	YE		13.97	44.18	771514
Ibbenbueren	DE		52.28	7.71	50577
Ibiporã	BR		-23.27	-51.05	51603
Ibirité	BR		-20.02	-44.06	170537
Ibitinga	BR		-21.76	-48.83	60033
Ibiúna	BR		-23.66	-47.22	75605
Ibshawāy	EG		29.36	30.68	86186
Ica	PE		-14.08	-75.73	282407
Ichalkaranji	IN		16.69	74.46	287353
Icheon-si	KR		37.28	127.44	196230
Ichihara	JP		35.52	140.08	283531
Ichikawa	JP		35.73	139.91	496676
Ichinomiya	JP		35.30	136.80	380073
Ichinoseki	JP		38.92	141.13	114476
Icó	BR		-6.40	-38.86	62642
Idah	NG		7.11	6.74	68703
Idaho Falls	US	Idaho	43.47	-112.03	59184
Idaiyarpālaiyam	IN		11.04	76.92	83908
Idanre	NG		7.11	5.12	86468
Idappadi	IN		11.59	77.84	54823
Idiofa	CD		-4.97	19.59	87882
Idkū	EG		31.31	30.30	177152
Idlib	SY		35.93	36.63	128840
Idylwood	US	Virginia	38.90	-77.21	17288
Ifakara	TZ		-8.13	36.68	205843
Ifo	NG		6.81	3.20	88272
Ifrane	MA		33.53	-5.11	73782
Iga	JP		34.76	136.13	88895
Iganga	UG		0.61	33.47	65500
Igarapé Miri	BR		-1.98	-48.96	64831
Igarassu	BR		-7.83	-34.91	122312
Igbara-Odo	NG		7.50	5.06	74121
Igbo-Ora	NG		7.43	3.29	92719
Igbo-Ukwu	NG		6.02	7.02	75224
Igboho	NG		8.84	3.76	136764
Igede-Ekiti	NG		7.67	5.13	87282
Iguala de la Independencia	MX		18.35	-99.54	118468
Iguatemi	BR		-23.61	-46.43	149700
Iguatu	BR		-6.36	-39.30	98064
Ihiala	NG		5.85	6.86	83265
Ihnāsyā al Madīnah	EG		29.09	30.94	68976
Ihnāsīyah	EG		29.09	31.02	64058
Iida	JP		35.52	137.82	101536
Iizuka	JP		33.64	130.69	126364
Ijebu Ode	NG		6.82	3.92	360000
Ijebu-Igbo	NG		6.97	4.00	109261
Ijebu-Jesa	NG		7.68	4.82	51730
Ijero-Ekiti	NG		7.82	5.07	167632
Ijok	MY		3.32	101.40	100899
Ijuí	BR		-28.39	-53.91	84780
Ikare	NG		7.53	5.75	465000
Ikeda	JP		34.82	135.43	104993
Ikeja	NG		6.60	3.34	313196
Ikere-Ekiti	NG		7.50	5.23	103054
Ikire	NG		7.37	4.19	222160
Ikirun	NG		7.91	4.67	134240
Ikom	NG		5.97	8.71	79103
Ikoma	JP		34.68	135.70	120741
Ikot Ekpene	NG		5.18	7.71	254806
Iksan	KR		35.94	126.95	307000
Ila Orangun	NG		8.02	4.90	179192
Ilagan	PH		17.15	121.89	164020
Ilchester	US	Maryland	39.25	-76.76	23476
Ile-des-Soeurs	CA		45.46	-73.55	20461
Ile-Ife	NG		7.48	4.56	560000
Ilebo	CD		-4.33	20.59	117245
Ilesa	NG		7.63	4.74	325000
Ilford	GB		51.56	0.07	168168
Ilhéus	BR		-14.80	-39.03	155499
Ilidža	BA		43.83	18.31	71277
Iligan	PH		8.23	124.24	342618
Iligan City	PH		8.25	124.40	312323
Ilioúpoli	GR		37.93	23.77	78153
Ilkal	IN		15.96	76.11	60242
Ilkeston	GB		52.97	-1.31	40953
Ilo	PE		-17.63	-71.34	53476
Ilobu	NG		7.84	4.49	118089
Iloilo	PH		10.70	122.56	473728
Ilorin	NG		8.50	4.54	1080000
Imabari	JP		34.07	133.00	170986
Imaichi	JP		36.72	139.68	64323
Imara Daima Estate	KE		-1.32	36.88	52837
Imarichō-kō	JP		33.27	129.88	57940
Imbituba	BR		-28.24	-48.67	52579
Imerintsiatosika	MG		-18.98	47.32	74085
Imizu	JP		36.77	137.13	90742
Immokalee	US	Florida	26.42	-81.42	24154
Imola	IT		44.36	11.71	69953
Impasugong	PH		8.31	125.00	55901
Imperatriz	BR		-5.53	-47.49	218106
Imperial	US	California	32.85	-115.57	17095
Imperial Beach	US	California	32.58	-117.11	27408
Imphal	IN		24.81	93.94	277196
Imus	PH		14.43	120.94	481949
Ina	JP		35.83	137.95	68177
Inada	JP		36.43	140.52	53502
Inagi	JP		35.63	139.50	93151
Inaruwa	NP		26.61	87.15	70093
Inazawa	JP		35.25	136.78	134751
Incheon	KR		37.46	126.71	3015482
Inda Silasē	ET		14.10	38.28	100100
Indaial	BR		-26.90	-49.23	71549
Indaiatuba	BR		-23.09	-47.21	256223
Indang	PH		14.20	120.88	70092
Independence	US	Missouri	39.09	-94.42	117255
Independence	US	Kentucky	38.94	-84.54	26819
Indian Trail	US	North Carolina	35.08	-80.67	37073
Indianapolis	US	Indiana	39.77	-86.16	887642
Indianola	US	Iowa	41.36	-93.56	15467
Indio	US	California	33.72	-116.22	87533
Indore	IN		22.72	75.83	1994397
Indramayu	ID		-6.33	108.32	123263
Inezgane	MA		30.36	-9.54	142320
Inglewood	US	California	33.96	-118.35	111666
Inglewood-Finn Hill	US	Washington	47.72	-122.23	22707
Ingolstadt	DE		48.77	11.42	120658
Ingombota	AO		-8.82	13.23	144911
Inhambane	MZ		-23.86	35.38	95388
Inhulets	UA		47.73	33.25	62173
Inhumas	BR		-16.36	-49.50	52204
Inisa	NG		7.85	4.33	164161
Inkisi	CD		-5.13	15.05	115317
Inkster	US	Michigan	42.29	-83.31	24672
Innisfil	CA		44.30	-79.65	43326
Innsbruck	AT		47.26	11.39	132493
Inongo	CD		-1.93	18.29	68852
Inowrocław	PL		52.80	18.26	77597
Insein	MM		16.89	96.10	247675
International City	AE		25.16	55.41	120000
Inuyama	JP		35.38	136.94	73995
Inver Grove Heights	US	Minnesota	44.85	-93.04	34857
Invercargill	NZ		-46.40	168.35	58000
Inverness	GB		57.48	-4.22	47790
Inzai	JP		35.83	140.16	105463
Iona	US	Florida	26.52	-81.96	15369
Iowa City	US	Iowa	41.66	-91.53	74220
Ioánnina	GR		39.66	20.85	65574
Ipatinga	BR		-19.47	-42.54	228746
Ipiales	CO		0.83	-77.64	77729
Ipiranga	BR		-23.60	-46.62	116271
Ipirá	BR		-12.16	-39.74	56876
Ipoh	MY		4.58	101.08	759952
Ipojuca	BR		-8.40	-35.06	105638
Ipoti	NG		7.87	5.08	82113
Ipswich	GB		52.06	1.16	178835
Iquique	CL		-20.21	-70.15	199587
Iquitos	PE		-3.75	-73.25	377609
Iranduba	BR		-3.28	-60.19	67114
Iranshahr	IR		27.20	60.68	131232
Irapuato	MX		20.67	-101.36	380941
Irati	BR		-25.47	-50.65	59250
Irbid	JO		32.56	35.85	569068
Irecê	BR		-11.30	-41.86	74507
Irewe	NG		6.42	3.14	139494
Iriga City	PH		13.43	123.41	115306
Iringa	TZ		-7.77	35.70	202490
Irkutsk	RU		52.30	104.29	623869
Irlam	GB		53.44	-2.42	19442
Irondequoit	US	New York	43.21	-77.58	51692
Irpin	UA		50.52	30.24	65167
Iruma	JP		35.82	139.37	147166
Irun	ES		43.34	-1.79	61983
Irvine	US	California	33.67	-117.82	256927
Irvine	GB		55.62	-4.66	34130
Irving	US	Texas	32.81	-96.95	236607
Irving Park	US	Illinois	41.95	-87.74	56520
Irvington	US	New Jersey	40.73	-74.23	61323
Irákleion	GR		35.33	25.14	137154
Isahaya	JP		32.84	130.04	135546
Ise	JP		34.48	136.70	123533
Ise-Ekiti	NG		7.46	5.42	190063
Isehara	JP		35.40	139.31	103401
Iselin	US	New Jersey	40.58	-74.32	18695
Iserlohn	DE		51.38	7.70	91811
Isesaki	JP		36.32	139.20	211850
Iseyin	NG		7.97	3.60	365300
Isfahan	IR		32.65	51.67	1547164
Isfara	TJ		40.13	70.63	274000
Ishikari	JP		43.24	141.35	58755
Ishim	RU		56.11	69.49	67762
Ishimbay	RU		53.45	56.04	70421
Ishinomaki	JP		38.42	141.30	140151
Ishioka	JP		36.18	140.27	73061
Ishwardi	BD		24.13	89.07	81995
Isidro Casanova	AR		-34.70	-58.59	131981
Isieke	NG		6.38	8.04	89990
Isiolo	KE		0.35	37.58	78650
Isiro	CD		2.77	27.62	255409
Iskandar Puteri	MY		1.39	103.62	575977
Iskitim	RU		54.64	83.30	61827
Isla Vista	US	California	34.41	-119.86	23096
Islamabad	PK		33.72	73.04	601600
Isle of Lewis	GB		58.22	-6.39	18500
Isleworth	GB		51.48	-0.34	25008
Islington	GB		51.54	-0.10	319143
Islington-City Centre West	CA		43.63	-79.54	43965
Islip	US	New York	40.73	-73.21	18689
Islāmpur	IN		26.27	88.19	55691
Ismailia	EG		30.60	32.27	429465
Isparta	TR		37.76	30.55	172334
Issaquah	US	Washington	47.53	-122.03	36081
Issia	CI		6.49	-6.59	68263
Issy-les-Moulineaux	FR		48.82	2.28	61447
Istanbul	TR		41.01	28.95	15701602
Istaravshan	TJ		39.91	69.00	273500
Isulan	PH		6.63	124.61	101455
Itabaiana	BR		-10.69	-37.43	103440
Itabashi	JP		35.75	139.71	584483
Itaberaba	BR		-12.53	-40.31	65073
Itabira	BR		-19.62	-43.23	113343
Itabirito	BR		-20.25	-43.80	53365
Itaboraí	BR		-22.74	-42.86	240040
Itabuna	BR		-14.79	-39.28	205660
Itacoatiara	BR		-3.14	-58.44	112520
Itaguaí	BR		-22.85	-43.78	123980
Itagüí	CO		6.18	-75.60	281853
Itaim Bibi	BR		-23.59	-46.68	101452
Itaim Paulista	BR		-23.50	-46.39	205295
Itaitinga	BR		-3.97	-38.53	64650
Itaituba	BR		-4.28	-55.98	123314
Itajaí	BR		-26.91	-48.66	155716
Itajubá	BR		-22.43	-45.45	93073
Itamaraju	BR		-17.04	-39.53	59605
Itami	JP		34.78	135.40	198138
Itanagar	IN		27.09	93.61	59490
Itanhaém	BR		-24.18	-46.79	103102
Itapecerica da Serra	BR		-23.72	-46.85	158522
Itapecuru Mirim	BR		-3.39	-44.36	60440
Itapema	BR		-27.09	-48.61	75940
Itaperuna	BR		-21.20	-41.89	107246
Itapetinga	BR		-15.25	-40.25	65897
Itapetininga	BR		-23.59	-48.05	157790
Itapeva	BR		-23.98	-48.88	89728
Itapevi	BR		-23.55	-46.93	240961
Itapipoca	BR		-3.49	-39.58	131123
Itapira	BR		-22.44	-46.82	72022
Itapoã	BR		-15.75	-47.77	65408
Itaquaquecetuba	BR		-23.49	-46.35	369275
Itaquera	BR		-23.53	-46.44	210960
Itatiba	BR		-23.01	-46.84	122581
Itauguá	PY		-25.39	-57.35	64997
Itaúna	BR		-20.08	-44.58	97669
Ithaca	US	New York	42.44	-76.50	30788
Itogon	PH		16.36	120.68	59736
Itoman	JP		26.13	127.67	61007
Itoshima	JP		33.54	130.18	98877
Itu	BR		-23.26	-47.30	137586
Ituiutaba	BR		-18.97	-49.46	102217
Itumbiara	BR		-18.42	-49.22	79582
Ituzaingó	AR		-27.59	-56.69	168419
Itārsi	IN		22.61	77.76	100574
Itō	JP		34.97	139.08	68773
Ivano-Frankivsk	UA		48.92	24.71	238196
Ivanovo	RU		57.00	40.97	406113
Ivanovskoye	RU		55.77	37.83	128000
Ivanteyevka	RU		55.97	37.92	51085
Ivato	MG		-18.80	47.48	52376
Ives Estates	US	Florida	25.96	-80.18	19525
Ivory Park	ZA		-26.00	28.20	184383
Ivry-sur-Seine	FR		48.82	2.38	57897
Iwade	JP		34.25	135.32	53967
Iwaki	JP		37.05	140.88	357309
Iwakuni	JP		34.16	132.22	129125
Iwamizawa	JP		43.20	141.76	85107
Iwata	JP		34.70	137.85	166672
Iwatsuki	JP		35.96	139.70	108833
Iwo	NG		7.64	4.18	250443
Ixelles	BE		50.83	4.37	86671
Ixtapa-Zihuatanejo	MX		17.64	-101.55	67408
Ixtapaluca	MX		19.32	-98.88	322271
Izhevsk	RU		56.85	53.20	648213
Izmayil	UA		45.35	28.84	69932
Izmaylovo	RU		55.80	37.78	104000
Iztacalco	MX		19.40	-99.10	384326
Iztapalapa	MX		19.36	-99.06	1835486
Izumi	JP		34.48	135.43	184615
Izumi	JP		32.08	130.37	51994
Izumisano	JP		34.42	135.32	100131
Izumiōtsu	JP		34.50	135.40	74412
Izumo	JP		35.37	132.77	172775
Içara	BR		-28.71	-49.30	59035
Iğdır	TR		39.92	44.05	101700
Iţsā	EG		29.24	30.79	74357
İnegol	TR		40.08	29.51	133959
İskenderun	TR		36.59	36.17	251682
İzmir	TR		38.41	27.14	2938292
İzmit	TR		40.76	29.93	196571
I‘zāz	SY		36.59	37.05	66138
Jabalpur	IN		23.17	79.95	1081677
Jabaquara	BR		-23.65	-46.65	214958
Jablah	SY		35.36	35.93	65915
Jaboatão dos Guararapes	BR		-8.11	-35.01	644037
Jaboticabal	BR		-21.25	-48.32	71821
Jabālyā	PS		31.53	34.48	168568
Jacareí	BR		-23.31	-45.97	213110
Jackson	US	Mississippi	32.30	-90.18	153701
Jackson	US	Tennessee	35.61	-88.81	66975
Jackson	US	New Jersey	39.78	-74.86	54856
Jackson	US	Michigan	42.25	-84.40	33133
Jackson Heights	US	New York	40.76	-73.89	67067
Jacksonville	US	Florida	30.33	-81.66	1009833
Jacksonville	US	North Carolina	34.75	-77.43	67357
Jacksonville	US	Arkansas	34.87	-92.11	28643
Jacksonville	US	Illinois	39.73	-90.23	19103
Jacksonville Beach	US	Florida	30.29	-81.39	23064
Jacmel	HT		18.24	-72.54	137966
Jacobabad	PK		28.28	68.44	219315
Jacobina	BR		-11.18	-40.51	82590
Jacona de Plancarte	MX		19.96	-102.31	53860
Jacundá	BR		-4.45	-49.12	59842
Jaffa	IL		32.05	34.75	100000
Jaffna	LK		9.67	80.01	169102
Jagdalpur	IN		19.08	82.02	125463
Jaggaiahpet	IN		16.89	80.10	53530
Jagraon	IN		30.79	75.47	65305
Jagtiāl	IN		18.79	78.92	103930
Jaguare	BR		-23.54	-46.75	55382
Jaguariúna	BR		-22.71	-46.99	58722
Jagüey Grande	CU		22.53	-81.13	54363
Jagādhri	IN		30.17	77.30	124894
Jahangira	PK		33.96	72.22	57011
Jahanian	PK		30.04	71.82	50318
Jahrom	IR		28.50	53.56	141634
Jahāngīrābād	IN		28.41	78.11	57363
Jahānābād	IN		25.21	84.99	103202
Jaigaon	IN		26.85	89.38	158664
Jaipur	IN		26.92	75.79	3046163
Jaisalmer	IN		26.92	70.90	67604
Jaitpur	IN		28.51	77.33	59330
Jakarta	ID		-6.21	106.85	8540121
Jalai Nur	CN		49.45	117.70	107828
Jalalpur Jattan	PK		32.64	74.21	146743
Jalalpur Pirwala	PK		29.51	71.22	500000
Jalandhar	IN		31.33	75.58	868929
Jalapa	GT		14.64	-89.99	159840
Jalgaon	IN		21.00	75.57	460228
Jalingo	NG		8.89	11.36	117757
Jalor	IN		25.35	72.62	54081
Jalpāiguri	IN		26.52	88.73	107832
Jalālābād	AF		34.43	70.45	271900
Jamaica	US	New York	40.69	-73.81	216866
Jamaica Plain	US	Massachusetts	42.31	-71.12	37468
Jambi City	ID		-1.60	103.62	635101
Jamestown	US	New York	42.10	-79.24	30075
Jamestown	US	North Dakota	46.91	-98.71	15422
Jamestown	SH		-15.92	-5.72	637
Jamkhandi	IN		16.50	75.29	68938
Jammu	IN		32.74	74.86	576198
Jamnagar	IN		22.47	70.07	600943
Jampur	PK		29.64	70.60	155243
Jamrud	PK		34.00	71.38	56642
Jamshedpur	IN		22.80	86.19	1339438
Jamālpur	BD		24.92	89.95	167900
Jamālpur	IN		25.31	86.49	105434
Jamūī	IN		24.93	86.23	87357
Janakpur	NP		26.73	85.93	195438
Janaúba	BR		-15.80	-43.31	70699
Jandira	BR		-23.53	-46.90	118045
Janesville	US	Wisconsin	42.68	-89.02	64123
Jangaon	IN		17.73	79.15	52394
Jangipur	IN		24.47	88.08	82548
Januária	BR		-15.48	-44.37	65150
Janzūr	LY		32.82	13.02	154389
Jaora	IN		23.64	75.13	74907
Japekrom	GH		7.58	-2.79	96000
Japeri	BR		-22.64	-43.65	102149
Jaraguá	BR		-23.44	-46.74	211610
Jaraguá do Sul	BR		-26.49	-49.07	182660
Jaramānā	SY		33.49	36.35	99999
Jaranwala	PK		31.33	73.42	150380
Jardim Angela	BR		-23.72	-46.77	311432
Jardim Botânico	BR		-15.87	-47.81	77767
Jardim Helena	BR		-23.48	-46.41	129409
Jardim Paulista	BR		-23.57	-46.66	83667
Jardim Sao Luis	BR		-23.68	-46.74	259377
Jardines de la Silla	MX		25.63	-100.19	53742
Jarrow	GB		54.98	-1.48	29470
Jaru	BR		-10.44	-62.47	50591
Jasmine Estates	US	Florida	28.29	-82.69	18989
Jasper	US	Indiana	38.39	-86.93	15451
Jastrzębie Zdrój	PL		49.96	18.57	95813
Jatani	IN		20.16	85.71	63697
Jataí	BR		-17.88	-51.72	105729
Jatibarang	ID		-6.47	108.32	73010
Jatiroto	ID		-7.88	111.12	50059
Jatiwangi	ID		-6.73	108.26	57973
Jauharabad	PK		32.29	72.28	113188
Jaunpur	IN		25.75	82.69	169572
Javānrūd	IR		34.81	46.49	54354
Jaworzno	PL		50.21	19.27	96541
Jayapura	ID		-2.53	140.72	410852
Jaçanã	BR		-23.46	-46.57	94609
Jaén	ES		37.77	-3.79	113457
Jaén	PE		-5.71	-78.81	52493
Jaú	BR		-22.30	-48.56	133497
Jebel Ali	AE		25.00	55.11	210000
Jeddah	SA		21.49	39.19	4697000
Jefferson City	US	Missouri	38.58	-92.17	42595
Jeffersontown	US	Kentucky	38.19	-85.56	26946
Jeffersonville	US	Indiana	38.28	-85.74	46960
Jega	NG		12.22	4.38	73495
Jeju City	KR		33.51	126.52	488844
Jelenia Góra	PL		50.90	15.73	77366
Jelgava	LV		56.65	23.71	54834
Jelutong	MY		5.39	100.32	63507
Jember	ID		-8.17	113.70	298585
Jena	DE		50.93	11.59	104712
Jendouba	TN		36.50	8.78	51408
Jenison	US	Michigan	42.91	-85.79	16538
Jenks	US	Oklahoma	36.02	-95.97	20740
Jeongeup	KR		35.60	126.92	139876
Jeonju	KR		35.82	127.15	638421
Jepara	ID		-6.59	110.67	1257912
Jequié	BR		-13.86	-40.09	127475
Jerez de la Frontera	ES		36.69	-6.14	212879
Jersey City	US	New Jersey	40.73	-74.08	264290
Jerusalem	IL		31.77	35.22	971800
Jessore	BD		23.17	89.21	243987
Jesus Maria	PE		-12.07	-77.04	66171
Jesús Menéndez	CU		21.16	-76.48	51002
Jetpur	IN		21.75	70.62	118302
Jette	BE		50.87	4.33	52490
Jeypore	IN		18.86	82.57	84830
Jhang Sadr	PK		31.27	72.32	606533
Jharia	IN		23.74	86.41	86938
Jharsuguda	IN		21.86	84.01	97730
Jhelum	PK		32.93	73.73	190425
Jhumri Telaiya	IN		24.43	85.53	87867
Jhunjhunūn	IN		28.13	75.40	118473
Jhālāwār	IN		24.60	76.16	66919
Jhānsi	IN		25.46	78.58	412927
Jhārgrām	IN		22.45	86.99	57796
Ji Paraná	BR		-10.89	-61.95	124333
Jiading	CN		31.39	121.24	1886100
Jiagedaqi	CN		50.42	124.12	135760
Jiamusi	CN		46.80	130.31	549549
Jianchang	CN		27.56	116.64	109108
Jiangbei	CN		29.73	106.64	60466
Jiangkou	CN		25.49	119.20	59902
Jiangmen	CN		22.58	113.08	1795459
Jiangshan	CN		36.68	120.53	86642
Jianguang	CN		28.19	115.78	61469
Jiangyan	CN		32.51	120.14	70375
Jiangyin	CN		31.91	120.26	1779515
Jiangyou	CN		31.77	104.72	127225
Jiangzhuang	CN		36.49	119.79	72453
Jiang’an	CN		28.73	105.07	67776
Jianshui	CN		24.28	101.22	490000
Jian’ou	CN		27.04	118.32	59187
Jiaohe	CN		43.72	127.33	123018
Jiaojiang	CN		28.70	121.47	470804
Jiaozhou	CN		36.28	120.00	619266
Jiaozuo	CN		35.24	113.24	865413
Jiashan	CN		30.85	120.93	137112
Jiawang	CN		34.43	117.44	133861
Jiaxing	CN		30.75	120.75	1180000
Jiayue	CN		36.02	119.18	93228
Jiayuguan	CN		39.81	98.29	231853
Jiazi	CN		22.88	116.07	130298
Jidd Ḩafş	BH		26.22	50.55	66588
Jidong	CN		45.26	131.12	58520
Jiehu	CN		35.54	118.45	69245
Jieshi	CN		22.81	115.83	137444
Jieshou	CN		33.26	115.36	141993
Jietou	CN		25.43	98.65	65843
Jiexiu	CN		37.02	111.91	77178
Jieyang	CN		23.54	116.37	1899394
Jihlava	CZ		49.40	15.59	50108
Jijel	DZ		36.82	5.76	131513
Jijiang	CN		29.29	106.25	196787
Jijiga	ET		9.35	42.80	483000
Jilin	CN		43.85	126.56	1895865
Jimeta	NG		9.28	12.46	248148
Jimma	ET		7.67	36.83	250900
Jimo	CN		36.39	120.46	70733
Jinan	CN		36.67	117.00	4335989
Jinchang	CN		38.50	102.19	228561
Jincheng	CN		35.50	112.83	476945
Jinding	CN		26.44	99.44	53667
Jinfeng	CN		28.24	116.60	127076
Jing'an	CN		34.50	116.92	57825
Jingdezhen	CN		29.29	117.21	473561
Jinggou	CN		36.28	119.55	62917
Jinghong	CN		22.00	100.77	205523
Jingling	CN		30.65	113.10	224871
Jingmen	CN		31.03	112.20	632954
Jingzhi	CN		36.31	119.39	126703
Jingzhou	CN		30.35	112.19	1052282
Jing’an	CN		31.22	121.42	936500
Jing’an	CN		22.21	113.29	186000
Jinhua	CN		29.11	119.64	1463990
Jinhua	CN		26.54	99.92	53523
Jining	CN		35.41	116.58	1241012
Jining	CN		41.03	113.11	258757
Jinja	UG		0.44	33.20	93061
Jinji	CN		23.23	110.83	56816
Jinjiang	CN		24.82	118.57	1416151
Jinjiang	CN		19.73	110.01	68720
Jinka	ET		5.65	36.65	54400
Jinniu	CN		25.80	100.57	96883
Jinotega	NI		13.09	-86.00	55000
Jinsha	CN		32.09	121.07	95647
Jinshan	CN		30.84	121.29	822776
Jinshanlu	CN		47.85	88.13	190064
Jinshi	CN		29.60	111.87	82906
Jinxiang	CN		27.43	120.61	84231
Jinzhong	CN		37.68	112.75	1226617
Jinzhou	CN		41.11	121.14	604269
Jinzhou	CN		39.10	121.72	215386
Jirapa	GH		10.54	-2.70	91279
Jishou	CN		28.32	109.73	102332
Jishu	CN		44.32	126.80	103988
Jishui	CN		33.73	115.40	77540
Jitai	CN		36.76	118.74	52144
Jitra	MY		6.27	100.42	63489
Jiudian	CN		36.99	120.20	97604
Jiujiang	CN		29.70	116.00	1164268
Jiupu	CN		41.07	122.95	123843
Jiuquan	CN		39.74	98.52	428346
Jiutai	CN		44.15	125.83	175115
Jiutepec	MX		18.88	-99.18	215357
Jixi	CN		45.29	130.96	403759
Jixian	CN		46.73	131.13	59160
Jiyuan	CN		35.09	112.59	242143
Jizan	SA		16.89	42.55	105198
Jizhou	CN		37.55	115.57	362013
Jizzax	UZ		40.13	67.83	179200
Ji’an	CN		27.12	114.98	538699
Jodhpur	IN		26.27	73.01	1056191
Joensuu	FI		62.60	29.76	78398
Johannesburg	ZA		-26.20	28.04	9418183
Johns Creek	US	Georgia	34.03	-84.20	83335
Johnson City	US	Tennessee	36.31	-82.35	66027
Johnston	US	Rhode Island	41.82	-71.51	29247
Johnston	US	Iowa	41.67	-93.70	20871
Johnstone	GB		55.83	-4.52	15930
Johnstown	US	Pennsylvania	40.33	-78.92	19966
Johor Bahru	MY		1.47	103.76	858118
Johor Jaya	MY		1.54	103.81	66000
Joint Base Pearl Harbor Hickam	US	Hawaii	21.35	-157.95	42184
Joinville	BR		-26.30	-48.85	461304
Joliet	US	Illinois	41.53	-88.08	147861
Joliette	CA		46.02	-73.42	34772
Jollyville	US	Texas	30.44	-97.78	16151
Jolo	PH		6.05	121.00	101002
Jombang	ID		-7.55	112.23	126465
Jomvu	KE		-3.99	39.61	163415
Jonesboro	US	Arkansas	35.84	-90.70	73907
Jonquière	CA		48.42	-71.25	54842
Joplin	US	Missouri	37.08	-94.51	51818
Jorhat	IN		26.76	94.20	126736
Jos	NG		9.93	8.89	1040000
Jose Bonifacio	BR		-23.57	-46.43	128243
Jose Rizal	PH		8.88	117.50	59040
José C. Paz	AR		-34.52	-58.77	230208
Jounieh	LB		33.98	35.62	96315
Joypur Hāt	BD		25.10	89.03	73068
João Monlevade	BR		-19.81	-43.17	80187
João Pessoa	BR		-7.12	-34.86	817511
Juan Díaz	PA		9.04	-79.44	100636
Juan-les-Pins	FR		43.57	7.11	60000
Juazeiro	BR		-9.41	-40.50	237821
Juazeiro do Norte	BR		-7.21	-39.32	225230
Juba	SS		4.85	31.58	450000
Juegang	CN		32.32	121.19	73317
Juhaynah	EG		26.67	31.50	76555
Juigalpa	NI		12.11	-85.37	50000
Juiz de Fora	BR		-21.76	-43.35	540756
Juja	KE		-1.10	37.01	156041
Juliaca	PE		-15.50	-70.13	245675
Junction City	US	Kansas	39.03	-96.83	24621
Jundiaí	BR		-23.19	-46.88	443221
Juneau	US	Alaska	58.30	-134.42	31555
Juniata Park	US	Pennsylvania	40.01	-75.11	17643
Junlian	CN		28.17	104.51	80708
Junín	AR		-34.59	-60.95	87509
Jupiter	US	Florida	26.93	-80.09	62707
Jurong East	SG		1.33	103.74	72960
Jurong Town	SG		1.33	103.72	262730
Jurong West	SG		1.35	103.72	253840
Jurupa Valley	US	California	33.99	-117.52	21930
Juruti	BR		-2.15	-56.09	50881
Jutiapa	GT		14.28	-89.89	145880
Juye	CN		35.39	116.07	58107
Jyväskylä	FI		62.24	25.72	148744
Jérémie	HT		18.65	-74.12	97503
Józsefváros	HU		47.49	19.07	76957
Jönköping	SE		57.78	14.16	112766
Jāfarābād	IN		28.68	77.27	54601
Jājmau	IN		26.43	80.41	652831
Jālaun	IN		26.15	79.34	55299
Jālna	IN		19.84	75.89	285577
Jāmuria	IN		23.70	87.08	160242
Jīnd	IN		29.32	76.32	167592
Jīroft	IR		28.68	57.74	130429
Jōetsu	JP		37.15	138.24	189430
Jōsō	JP		36.04	139.96	60834
Jōyō	JP		34.84	135.81	74607
Jūnāgadh	IN		21.52	70.46	319462
Jūrmala	LV		56.97	23.77	52001
Kaambooni	SO		-1.64	41.59	79000
Kabale	UG		-1.25	29.99	53200
Kabalo	CD		-6.05	26.91	81191
Kabanjahe	ID		3.10	98.49	73581
Kabankalan	PH		9.98	122.81	210893
Kabbasin	SY		36.43	37.57	51230
Kabin Buri	TH		13.95	101.72	140056
Kabinda	CD		-6.14	24.48	219396
Kabirwala	PK		30.40	71.86	91932
Kabul	AF		34.53	69.17	4434550
Kabwe	ZM		-14.45	28.45	288598
Kadapa	IN		14.48	78.82	344893
Kadayanallur	IN		9.07	77.34	90364
Kadi	IN		23.30	72.33	81404
Kadiri	IN		14.11	78.16	89429
Kadirli	TR		37.37	36.10	70248
Kadiyivka	UA		48.57	38.64	73248
Kadoma	JP		34.74	135.57	131727
Kadoma	ZW		-18.33	29.92	117381
Kadugli	SD		11.01	29.72	87666
Kaduna	NG		10.53	7.44	1850000
Kaech’ŏn	KP		39.70	125.89	319554
Kaesŏng	KP		37.97	126.55	338155
Kafanchan	NG		9.58	8.29	79522
Kaffrine	SN		14.11	-15.55	57307
Kafr ad Dawwār	EG		31.13	30.13	128539
Kafr ash Shaykh	EG		31.11	30.94	194569
Kafr az Zayyāt	EG		30.82	30.82	83348
Kafrul	BD		23.79	90.37	339734
Kafue	ZM		-15.77	28.18	104174
Kaga	JP		36.30	136.33	67793
Kaga-Bandoro	CF		6.99	19.19	55047
Kagaznāgār	IN		19.33	79.47	57583
Kageleke	CN		37.30	79.60	75730
Kagoro	NG		9.61	8.39	77008
Kagoshima	JP		31.57	130.55	595049
Kahama	TZ		-3.83	32.60	453654
Kahna Nau	PK		31.37	74.37	79301
Kahnūj	IR		27.94	57.70	52624
Kahramanmaraş	TR		37.58	36.93	384953
Kahror Pakka	PK		29.62	71.91	69743
Kahului	US	Hawaii	20.89	-156.47	26337
Kai	JP		35.68	138.51	75313
Kaifeng	CN		34.80	114.31	1451741
Kaihua	CN		23.37	104.28	64404
Kaili	CN		26.59	107.98	275745
Kailua	US	Hawaii	21.40	-157.74	38635
Kaimukī	US	Hawaii	21.28	-157.80	20878
Kairouan	TN		35.68	10.10	139070
Kairāna	IN		29.40	77.21	80432
Kaiserslautern	DE		49.44	7.77	98732
Kaithal	IN		29.80	76.40	144915
Kaitong	CN		44.81	123.08	62537
Kaiyuan	CN		23.70	103.30	198423
Kaiyuan	CN		42.53	124.04	112462
Kaizuka	JP		34.45	135.35	92632
Kajang	MY		2.99	101.79	236240
Kajansi	UG		0.22	32.53	135600
Kakamega	KE		0.28	34.75	1867579
Kakamigahara	JP		35.42	136.87	144521
Kakata	LR		6.53	-10.35	52247
Kakegawa	JP		34.77	138.02	117925
Kakogawachō-honmachi	JP		34.77	134.83	271634
Kalaban Koro	ML		12.57	-8.03	148247
Kalaburagi	IN		17.34	76.84	543147
Kalamansig	PH		6.55	124.05	52257
Kalamariá	GR		40.58	22.95	91518
Kalamassery	IN		10.06	76.33	71038
Kalamata	GR		37.04	22.11	54100
Kalamazoo	US	Michigan	42.29	-85.59	76041
Kalasin	TH		16.43	103.51	55102
Kalaw	MM		20.63	96.56	93032
Kalemie	CD		-5.95	29.19	160961
Kalemyo	MM		23.19	94.06	348573
Kalgoorlie	AU		-30.75	121.47	29072
Kalibo (poblacion)	PH		11.71	122.36	89127
Kalihi Valley	US	Hawaii	21.36	-157.84	20647
Kalihi-Palama	US	Hawaii	21.33	-157.88	43805
Kalima	CD		-5.49	28.22	72327
Kaliningrad	RU		54.71	20.51	475056
Kalininskiy	RU		60.00	30.39	504641
Kalispell	US	Montana	48.20	-114.31	22052
Kalisz	PL		51.76	18.09	108759
Kallakurichi	IN		11.73	78.96	1682687
Kallang	SG		1.33	103.87	101290
Kallangur	AU		-27.25	152.99	20222
Kallithéa	GR		37.95	23.70	100641
Kalmiuskyi	UA		47.11	37.54	101498
Kalmunai	LK		7.41	81.83	100171
Kalol	IN		23.25	72.50	134426
Kaluga	RU		54.53	36.27	340851
Kalulushi	ZM		-12.84	28.09	104046
Kalush	UA		49.02	24.37	65088
Kalyani	IN		22.98	88.43	93184
Kalynivskyi	UA		48.01	37.85	103249
Kalyān	IN		19.24	73.14	1262255
Kamagaya	JP		35.77	140.00	109932
Kamakura	JP		35.31	139.55	172929
Kamalia	PK		30.73	72.65	166617
Kambar	PK		27.59	68.00	77481
Kambove	CD		-10.87	26.60	99884
Kamensk-Shakhtinsky	RU		48.32	40.26	75814
Kamensk-Ural’skiy	RU		56.41	61.93	182500
Kameoka	JP		35.00	135.58	97181
Kamifukuoka	JP		35.87	139.51	52323
Kamigyō-ku	JP		35.03	135.76	83000
Kamina	CD		-8.74	25.00	200184
Kamirenjaku	JP		35.69	139.55	195391
Kamisu	JP		35.90	140.67	95454
Kamloops	CA		50.67	-120.32	104460
Kamoke	PK		31.98	74.22	292023
Kampala	UG		0.32	32.58	1680600
Kamphaeng Phet	TH		16.48	99.52	58787
Kampong Baharu Cheras Batu Sebelas	MY		3.05	101.77	232100
Kampong Cham	KH		11.99	105.46	61750
Kampong Chhnang	KH		12.25	104.67	75244
Kampong Dungun	MY		3.22	101.32	58674
Kampong Pasir Ris	SG		1.38	103.93	144260
Kampong Sidam	MY		5.53	100.57	60983
Kampung Baru Balakong	MY		3.03	101.75	69302
Kampung Baru Subang	MY		3.15	101.53	833571
Kampung Bukit Baharu	MY		2.22	102.29	55656
Kampung Kangkar Teberau	MY		1.53	103.75	412373
Kampung Larkin Lama	MY		1.50	103.74	500000
Kampung Manjoi	MY		4.62	101.07	86266
Kampung Pasir Gudang Baru	MY		1.47	103.88	145639
Kampung Sungai Ara	MY		5.33	100.27	140849
Kampung Sungai Glugur	MY		5.37	100.31	145600
Kampung Sungai Kajang	MY		3.42	101.17	84031
Kamsar	GN		10.65	-14.62	113350
Kamuli	UG		0.95	33.12	67800
Kamyanets-Podilskyi	UA		48.68	26.59	97908
Kamyanske	UA		48.52	34.61	226845
Kamyshin	RU		50.09	45.41	128626
Kamālshahr	IR		35.86	50.87	141669
Kanakapura	IN		12.55	77.42	54014
Kanaker-Zeytun	AM		40.22	44.54	75500
Kananga	CD		-5.90	22.42	1247168
Kanasín	MX		20.93	-89.56	77240
Kanata	CA		45.30	-75.92	90000
Kanayannur	IN		9.97	76.27	851406
Kanazawa	JP		36.60	136.62	466029
Kanbe	MM		16.71	96.00	58146
Kanchanaburi	TH		14.00	99.55	63699
Kanchipuram	IN		12.84	79.70	221715
Kandahār	AF		31.61	65.71	523300
Kandhkot	PK		28.25	69.18	99155
Kandi	BJ		11.13	2.94	56043
Kandukūr	IN		15.22	79.90	57246
Kandy	LK		7.29	80.63	111701
Kaneohe	US	Hawaii	21.40	-157.80	34597
Kangar	MY		6.44	100.20	63869
Kangding	CN		30.00	101.96	100000
Kanggye	KP		40.97	126.59	209530
Kangnyŏng	KP		37.91	125.51	106827
Kangsŏn	KP		38.94	125.58	102436
Kangāvar	IR		34.50	47.97	51352
Kanhangad	IN		12.31	75.11	125564
Kani	JP		35.40	137.06	102143
Kanjia	CN		36.37	119.58	75669
Kankakee	US	Illinois	41.12	-87.86	26676
Kankan	GN		10.39	-9.31	221428
Kannapolis	US	North Carolina	35.49	-80.62	46144
Kannauj	IN		27.06	79.92	76714
Kannur	IN		11.87	75.36	62836
Kano	NG		12.00	8.52	4910000
Kanoya	JP		31.38	130.85	101096
Kanpur	IN		26.47	80.35	2823249
Kanpur Cantonment	IN		26.46	80.38	108534
Kansas City	US	Missouri	39.10	-94.58	475378
Kansas City	US	Kansas	39.11	-94.63	152933
Kansk	RU		56.20	95.72	101502
Kanuma	JP		36.55	139.73	94903
Kanyama	CD		-7.52	24.17	80043
Kan’onjichō	JP		34.13	133.65	57438
Kaohsiung	TW		22.62	120.31	2737660
Kaolack	SN		14.15	-16.07	298904
Kapar	MY		3.13	101.38	269627
Kapchorwa	UG		1.40	34.45	51200
Kapenguria	KE		1.24	35.11	56000
Kapiri Mposhi	ZM		-13.97	28.67	83211
Kapolei	US	Hawaii	21.34	-158.06	15186
Kapolei Villages	US	Hawaii	21.34	-158.07	15408
Kaposvár	HU		46.37	17.80	64280
Kapurthala Town	IN		31.38	75.38	98916
Kara	TG		9.55	1.19	104207
Karabağlar	TR		38.38	27.13	479338
Karabük	TR		41.20	32.63	125403
Karachi	PK		24.86	67.01	11624219
Karagandy	KZ		49.80	73.10	497777
Karaj	IR		35.83	50.99	1448075
Karakol	KG		42.49	78.39	84351
Karaman	TR		37.18	33.22	175390
Karamay	CN		45.58	84.89	261445
Karangsembung	ID		-6.85	108.64	75856
Karatsu	JP		33.44	129.97	117663
Karauli	IN		26.50	77.03	82960
Karawang	ID		-6.31	107.32	307880
Karbala	IQ		32.62	44.02	1218732
Kariega	ZA		-33.76	25.40	291052
Kariya	JP		34.98	136.98	153834
Kariya	JP		34.75	134.39	52015
Karlskrona	SE		56.16	15.59	66675
Karlsruhe	DE		49.01	8.40	283799
Karlstad	SE		59.38	13.50	61492
Karnaphuli	BD		22.69	92.23	203697
Karnāl	IN		29.69	76.98	302140
Karol Bāgh	IN		28.65	77.19	505241
Karonga	MW		-9.93	33.93	69486
Karori	NZ		-41.28	174.74	15380
Karratha	AU		-20.74	116.85	17013
Kars	TR		40.60	43.09	91450
Kartasura	ID		-7.55	110.74	88927
Karur	IN		10.96	78.08	234191
Karuri	KE		-1.18	36.76	194342
Karuri	KE		-0.70	37.18	194342
Karwar	IN		14.81	74.13	77139
Karād	IN		17.29	74.18	55663
Karāwalnagar	IN		28.73	77.27	224281
Karīmganj	IN		24.87	92.36	56854
Karīmnagar	IN		18.44	79.13	289821
Karşıyaka	TR		38.46	27.11	339624
Kas	SD		12.51	24.29	55255
Kasama	ZM		-10.21	31.18	179636
Kasama	JP		36.38	140.27	73664
Kasangati	UG		0.44	32.60	207800
Kasaoka	JP		34.51	133.50	50160
Kasba Tadla	MA		32.60	-6.27	51697
Kasese	UG		0.18	30.08	115400
Kashan	IR		33.98	51.43	304487
Kashgar	CN		39.47	75.99	506640
Kashiba	JP		34.53	135.71	78113
Kashihara	JP		34.58	135.62	79058
Kashihara-shi	JP		34.51	135.79	124521
Kashima-shi	JP		35.97	140.64	66950
Kashipur	IN		29.21	78.96	103138
Kashiwa	JP		35.86	139.98	433436
Kashiwara	JP		34.45	135.77	120922
Kashiwazaki	JP		37.37	138.55	86183
Kasihan	ID		-7.83	110.33	86234
Kasoa	GH		5.53	-0.42	86753
Kasongo	CD		-4.43	26.67	81629
Kaspiysk	RU		42.88	47.64	81752
Kassala	SD		15.45	36.40	401477
Kassel	DE		51.32	9.50	197230
Kasserine	TN		35.17	8.84	84365
Kastamonu	TR		41.38	33.78	125622
Kasuga	JP		33.53	130.46	111023
Kasugai	JP		35.25	136.97	308681
Kasukabe	JP		35.98	139.75	229792
Kasulu	TZ		-4.58	30.10	238321
Kasungu	MW		-13.03	33.48	66152
Kasur	PK		31.12	74.45	510875
Katabi	UG		0.08	32.47	154300
Katanawa	JP		33.52	130.42	50112
Katano	JP		34.79	135.69	75033
Kateríni	GR		40.27	22.51	53293
Kathmandu	NP		27.70	85.32	1442271
Kathua	IN		32.37	75.53	59866
Kati	ML		12.74	-8.07	130254
Katihar	IN		25.54	87.57	240838
Katiola	CI		8.14	-5.10	59641
Katori-shi	JP		35.90	140.50	74469
Katoro	TZ		-3.00	31.93	75000
Katowice	PL		50.26	19.02	286960
Katsina	NG		12.99	7.60	670000
Katsushika	JP		35.73	139.85	453093
Katsuta	JP		36.38	140.53	155968
Kattaqo’rg’on Shahri	UZ		39.91	66.27	90600
Katumba	TZ		-9.23	33.62	108558
Katunayaka	LK		7.17	79.89	84643
Katwa	CD		0.09	29.31	89352
Katy	US	Texas	29.79	-95.82	16158
Kaukauna	US	Wisconsin	44.28	-88.27	15854
Kaunas	LT		54.90	23.91	289380
Kaura Namoda	NG		12.59	6.59	69725
Kavaklı	TR		41.09	28.33	50502
Kavanur	IN		13.00	80.08	54986
Kavála	GR		40.94	24.41	54027
Kawachi-Nagano	JP		34.44	135.58	101692
Kawagoe	JP		35.91	139.49	354571
Kawaguchi	JP		35.81	139.71	607373
Kawalu	ID		-7.38	108.21	50541
Kawanishi	JP		34.82	135.42	155165
Kawasaki	JP		35.52	139.72	1538262
Kawit	PH		14.44	120.90	73210
Kawm Ḩamādah	EG		30.76	30.70	55652
Kawthoung	MM		9.98	98.55	57949
Kaya	BF		13.09	-1.08	121970
Kayamkulam	IN		9.18	76.50	68634
Kayes	ML		14.45	-11.44	194716
Kayes	CG		-4.20	13.29	58737
Kayna	CD		-0.61	29.17	51103
Kayseri	TR		38.73	35.49	1452458
Kaysville	US	Utah	41.04	-111.94	30472
Kazan	RU		55.79	49.12	1243500
Kazo	JP		36.12	139.60	112792
Kaédi	MR		16.15	-13.51	56283
Kearney	US	Nebraska	40.70	-99.08	33021
Kearns	US	Utah	40.66	-112.00	35731
Kearny	US	New Jersey	40.77	-74.15	42137
Kebomas	ID		-7.17	112.63	75982
Kecskemét	HU		46.91	19.69	109847
Kediri	ID		-7.82	112.02	301424
Kedungwaru	ID		-8.07	111.92	80257
Kedungwuni	ID		-6.97	109.65	117249
Keelung	TW		25.13	121.74	362487
Keene	US	New Hampshire	42.93	-72.28	23265
Keffi	NG		8.85	7.87	85911
Keighley	GB		53.87	-1.91	50171
Keilor East	AU		-37.73	144.87	15078
Keizer	US	Oregon	44.99	-123.03	37895
Kelaa Kebira	TN		35.87	10.54	63264
Kelar	IQ		34.63	45.32	250000
Kelenföld	HU		47.47	19.03	53332
Keller	US	Texas	32.93	-97.25	45758
Kellyville	AU		-33.71	150.95	27676
Kelo	TD		9.31	15.81	82677
Kelowna	CA		49.88	-119.49	144576
Kembangan	SG		1.32	103.91	130252
Kemerovo	RU		55.35	86.10	558973
Kempas	MY		1.55	103.70	62011
Kempston	GB		52.12	-0.50	19873
Kempston Hardwick	GB		52.09	-0.50	20000
Kempten (Allgäu)	DE		47.73	10.31	61399
Ken Caryl	US	Colorado	39.58	-105.11	32438
Kendal	GB		54.33	-2.75	29147
Kendale Lakes	US	Florida	25.71	-80.41	56148
Kendall	US	Florida	25.68	-80.32	80241
Kendall West	US	Florida	25.71	-80.44	36154
Kendari	ID		-3.98	122.52	351085
Kenema	SL		7.88	-11.19	255110
Kenge	CD		-5.77	13.66	63317
Kenilworth	GB		52.35	-1.58	22413
Keningau	MY		5.34	116.16	77650
Kenitra	MA		34.26	-6.58	470949
Kenmore	US	Washington	47.76	-122.24	22030
Kenmore	US	New York	42.97	-78.87	15160
Kennedy	CO		4.62	-74.15	979914
Kennedy Park	CA		43.72	-79.26	17123
Kennedy Street	US	District of Columbia	38.96	-77.02	15251
Kenner	US	Louisiana	29.99	-90.24	67091
Kennesaw	US	Georgia	34.02	-84.62	33584
Kennewick	US	Washington	46.21	-119.14	78896
Kenora	CA		49.77	-94.49	15096
Kenosha	US	Wisconsin	42.58	-87.82	99858
Kensington	US	New York	40.65	-73.97	39120
Kensington	GB		53.41	-2.95	16522
Kensington	AU		-33.92	151.22	15021
Kensington-Cedar Cottage	CA		49.25	-123.07	49235
Kensington-Chinatown	CA		43.65	-79.40	17945
Kent	US	Washington	47.38	-122.23	126952
Kent	US	Ohio	41.15	-81.36	29810
Kentau	KZ		43.52	68.50	57408
Kentron	AM		40.18	44.51	133000
Kentwood	US	Michigan	42.87	-85.64	51357
Kenwood	US	Illinois	41.81	-87.60	17601
Keonjhargarh	IN		21.63	85.60	60590
Kepanjen	ID		-8.13	112.57	51919
Kepong	MY		3.21	101.64	85960
Keratsíni	GR		37.96	23.62	77077
Kerch	UA		45.36	36.48	148932
Keren	ER		15.78	38.45	74800
Kericho	KE		-0.37	35.28	53804
Kerman	IR		30.28	57.08	577514
Kermanshah	IR		34.31	47.06	621100
Kernersville	US	North Carolina	36.12	-80.07	23811
Kerpen	DE		50.87	6.70	64226
Kerrville	US	Texas	30.05	-99.14	23136
Kertosono	ID		-7.58	112.10	60782
Kesennuma	JP		38.90	141.58	61147
Keshod	IN		21.30	70.25	76193
Kesklinn	EE		59.44	24.76	67766
Keswick	CA		44.25	-79.47	21000
Kettering	GB		52.40	-0.73	56676
Kettering	US	Ohio	39.69	-84.17	55525
Keur Médoune	SN		14.76	-15.90	77255
Kew	AU		-37.81	145.03	24499
Kew Gardens	US	New York	40.71	-73.83	18983
Kew Gardens Hills	US	New York	40.73	-73.82	37479
Key West	US	Florida	24.56	-81.78	25755
Keynsham	GB		51.41	-2.50	19603
Keysborough	AU		-37.99	145.17	30018
Keystone	US	Florida	28.16	-82.62	24039
Kfar Saba	IL		32.17	34.91	110456
Khabarovsk	RU		48.46	135.10	618150
Khadki	IN		18.56	73.85	75654
Khagaul	IN		25.58	85.05	51577
Khagrachhari	BD		23.11	91.97	50364
Khairpur Mir’s	PK		27.53	68.76	191044
Khajoori Khas	IN		28.71	77.26	76640
Khalifah A City	AE		24.43	54.60	85374
Khalkhāl	IR		37.62	48.53	51024
Khalándrion	GR		38.02	23.80	74192
Khambhāt	IN		22.32	72.62	99164
Khamis Mushait	SA		18.30	42.73	387553
Khammam	IN		17.25	80.14	196283
Khan Na Yao	TH		13.83	100.68	88678
Khanabad	AF		36.68	69.11	71531
Khanapuram Haveli	IN		17.26	80.17	53442
Khandwa	IN		21.82	76.35	200738
Khanna	IN		30.71	76.22	128137
Khanpur	PK		28.65	70.66	142426
Khanty-Mansiysk	RU		61.00	69.03	101466
Khanzhonkivskyi	UA		48.10	38.04	53040
Kharagpur	IN		22.34	87.33	219665
Kharakvasla	IN		18.44	73.78	78684
Kharar	IN		30.75	76.65	74460
Khardah	IN		22.72	88.38	128346
Kharghar	IN		19.05	73.07	80612
Khargone	IN		21.82	75.61	116150
Kharian	PK		32.82	73.89	103036
Kharkiv	UA		49.98	36.25	1421125
Kharkivskyi Masyv	UA		50.41	30.66	93700
Khartoum	SD		15.55	32.53	1974647
Khartoum North	SD		15.65	32.53	1012211
Khartsyzk	UA		48.04	38.14	56182
Khasavyurt	RU		43.25	46.59	126829
Khasnahzān	IQ		36.20	44.14	146639
Khatauli	IN		29.28	77.73	64731
Khemis Miliana	DZ		36.26	2.22	80512
Khemisset	MA		33.82	-6.07	143640
Khenchela	DZ		35.44	7.14	114472
Khenifra	MA		32.93	-5.66	128318
Kherson	UA		46.64	32.61	66000
Khewra	PK		32.65	73.01	80000
Khimki	RU		55.90	37.43	239967
Khirdalan	AZ		40.45	49.76	196200
Khlong Chan	TH		13.78	100.65	76934
Khlong Kum	TH		13.79	100.68	69071
Khlong Luang	TH		14.06	100.65	118551
Khlong Sam Wa	TH		13.87	100.74	169489
Khlong San	TH		13.73	100.51	73263
Khlong Toei	TH		13.71	100.58	109041
Khmelnytskyi	UA		49.42	26.98	274452
Khobar	SA		26.28	50.21	165799
Khomeyn	IR		33.64	50.08	77425
Khomeynī Shahr	IR		32.69	51.54	277334
Khon Kaen	TH		16.45	102.83	114459
Khopoli	IN		18.79	73.35	71141
Khoroshëvo-Mnevniki	RU		55.78	37.47	159000
Khorramabad	IR		33.49	48.36	329825
Khorramdarreh	IR		36.21	49.20	50528
Khorramshahr	IR		30.44	48.18	330606
Khouribga	MA		32.88	-6.91	214241
Khrustalnyi	UA		48.14	38.92	79533
Khujand	TJ		40.28	69.62	191000
Khulm	AF		36.70	67.70	64933
Khulna	BD		22.81	89.56	1500689
Khurai	IN		24.04	78.33	51108
Khurarianwala	PK		31.50	73.27	96743
Khuraybat as Sūq	JO		31.88	35.92	186158
Khurja	IN		28.25	77.86	105909
Khushāb	PK		32.30	72.35	102793
Khuzdar	PK		27.81	66.61	218112
Khwisero	KE		0.17	34.59	113294
Khāliş	IQ		33.81	44.53	70046
Khāmgaon	IN		20.71	76.57	94604
Khān Yūnis	PS		31.34	34.31	173183
Khānaqīn	IQ		34.35	45.39	175000
Khāsh	IR		28.22	61.22	69603
Khōst	AF		33.34	69.92	96123
Khūy	IR		38.55	44.95	198845
Kiambu	KE		-1.17	36.84	147870
Kibaha	TZ		-6.77	38.92	265360
Kibaigwa	TZ		-6.08	36.65	50054
Kidapawan	PH		7.01	125.09	79652
Kidderminster	GB		52.39	-2.25	57400
Kidsgrove	GB		53.09	-2.24	29480
Kiel	DE		54.32	10.13	252668
Kielce	PL		50.87	20.63	192468
Kiffa	MR		16.62	-11.40	62051
Kigali	RW		-1.95	30.06	1132686
Kigoma	TZ		-4.88	29.63	232388
Kikolo	AO		-8.78	13.33	728205
Kikuyu	KE		-1.25	36.66	323881
Kikwit	CD		-5.04	18.82	509367
Kilamba	AO		-8.85	13.28	237528
Kilburn	GB		51.55	-0.19	29027
Kilifi	KE		-3.63	39.85	74270
Kilis	TR		36.72	37.12	111648
Kilju	KP		40.96	129.33	63652
Kilkenny	IE		52.65	-7.25	21589
Killarney	CA		49.23	-123.04	29325
Killeen	US	Texas	31.12	-97.73	140806
Killingly Center	US	Connecticut	41.84	-71.87	17282
Kilmarnock	GB		55.61	-4.50	46970
Kilosa	TZ		-6.83	36.98	91889
Kilwinning	GB		55.65	-4.71	16100
Kima Kieza	AO		-8.83	13.30	428855
Kimberley	ZA		-28.73	24.76	142089
Kimhae	KR		35.23	128.88	531966
Kimilili	KE		0.79	34.72	56050
Kimitsu	JP		35.35	139.87	83058
Kimpese	CD		-5.56	14.43	79539
Kimry	RU		56.87	37.36	52070
Kindia	GN		10.06	-12.87	161024
Kindrativskyi	UA		48.30	38.05	101565
Kindu	CD		-2.94	25.92	234651
Kineshma	RU		57.44	42.13	92983
King Faisal Military City	SA		28.45	45.97	65000
King of Prussia	US	Pennsylvania	40.09	-75.40	19936
King's Lynn	GB		52.75	0.40	46093
Kingisepp	RU		59.38	28.61	50566
Kingman	US	Arizona	35.19	-114.05	28912
Kings Bridge	US	New York	40.88	-73.91	75132
Kings Park	US	New York	40.89	-73.26	17282
Kingsessing	US	Pennsylvania	39.94	-75.23	19668
Kingsford	AU		-33.92	151.23	15338
Kingsland	US	Georgia	30.80	-81.69	16487
Kingsport	US	Tennessee	36.55	-82.56	53014
Kingston	JM		18.00	-76.79	937700
Kingston	CA		44.23	-76.48	132485
Kingston	US	New York	41.93	-74.00	23436
Kingston	NF		-29.05	167.97	880
Kingston upon Hull	GB		53.74	-0.34	314018
Kingstown	VC		13.16	-61.23	24518
Kingsview Village-The Westway	CA		43.70	-79.55	22000
Kingsville	US	Texas	27.52	-97.86	26225
Kingsville	CA		42.10	-82.73	22119
Kingswinford	GB		52.50	-2.17	20000
Kingswood	GB		51.45	-2.51	40734
Kinokawa	JP		34.27	135.41	60592
Kinshasa	CD		-4.33	15.31	16000000
Kinston	US	North Carolina	35.26	-77.58	21337
Kintampo	GH		8.06	-1.73	53711
Kippax	GB		53.77	-1.37	15965
Kipushi	CD		-11.76	27.25	169635
Kira	UG		0.40	32.63	462900
Kirdāsah	EG		30.03	31.11	137588
Kirishi	RU		59.47	32.04	56190
Kirishima	JP		31.74	130.76	123205
Kirkby	GB		53.48	-2.89	45564
Kirkby in Ashfield	GB		53.10	-1.24	27539
Kirkcaldy	GB		56.12	-3.16	50370
Kirkdale	GB		53.43	-2.98	18657
Kirkintilloch	GB		55.94	-4.15	19630
Kirkland	US	Washington	47.68	-122.21	87281
Kirkland	CA		45.45	-73.87	20491
Kirksville	US	Missouri	40.19	-92.58	17520
Kirkuk	IQ		35.47	44.39	1031000
Kirkwood	US	Missouri	38.58	-90.41	27750
Kirov	RU		58.60	49.66	507155
Kirovo-Chepetsk	RU		58.55	50.03	90252
Kirumba	CD		-1.09	29.29	52041
Kirwan	AU		-19.30	146.73	21034
Kiryas Joel	US	New York	41.34	-74.17	32954
Kiryat Gat	IL		31.61	34.76	61817
Kiryū	JP		36.40	139.33	108991
Kirāri Sulemānnagar	IN		28.70	77.06	283211
Kisangani	CD		0.52	25.19	1181788
Kisaran	ID		2.98	99.62	141915
Kisarazu	JP		35.38	139.93	136166
Kisela Voda	MK		41.95	21.50	58216
Kiselëvsk	RU		53.99	86.66	104000
Kiserian	KE		-1.43	36.69	76903
Kishanganj	IN		26.10	87.96	105782
Kishangarh	IN		26.59	74.85	154886
Kishiwada	JP		34.47	135.37	205561
Kishorganj	BD		24.44	90.78	90690
Kisi	NG		9.08	3.85	155510
Kisii	KE		-0.68	34.77	112417
Kisilevsk	RU		54.00	86.65	83431
Kislovodsk	RU		43.91	42.72	132771
Kismayo	SO		-0.36	42.55	234852
Kispest	HU		47.45	19.14	61453
Kissidougou	GN		9.18	-10.10	116019
Kissimmee	US	Florida	28.30	-81.42	69152
Kisumu	KE		-0.10	34.76	397957
Kita	JP		35.75	139.73	332140
Kita	ML		13.04	-9.49	75598
Kitahiroshima	JP		42.98	141.57	58918
Kitakami	JP		39.28	141.12	93045
Kitakyushu	JP		33.85	130.85	940978
Kitale	KE		1.02	35.01	162174
Kitami	JP		43.80	143.89	119135
Kitamoto	JP		36.03	139.54	66022
Kitanagoya	JP		35.25	136.88	86385
Kitchener	CA		43.43	-80.51	256885
Kitengela	KE		-1.48	36.96	154436
Kitgum	UG		3.28	32.89	56891
Kitsilano	CA		49.27	-123.17	43045
Kituku	CD		-7.58	30.21	66378
Kitwe	ZM		-12.80	28.21	665961
Kiyose	JP		35.78	139.53	76208
Kiyosu	JP		35.22	136.83	67352
Kizlyar	RU		43.85	46.71	50564
Kizugawa	JP		34.74	135.84	77907
Kiến An	VN		20.81	106.63	118047
Kladno	CZ		50.15	14.10	69664
Klaeng	TH		12.78	101.65	55619
Klagenfurt am Wörthersee	AT		46.62	14.31	100316
Klaipėda	LT		55.71	21.14	172292
Klamath Falls	US	Oregon	42.22	-121.78	21399
Klang	MY		3.04	101.44	240016
Klangenan	ID		-6.71	108.44	88378
Klaten	ID		-7.71	110.61	126831
Klerksdorp	ZA		-26.85	26.67	227039
Klimovsk	RU		55.36	37.53	55206
Klin	RU		56.33	36.73	80778
Klinteby Frihed	DK		55.20	11.60	53443
Klintsy	RU		52.76	32.24	66336
Kluang	MY		2.03	103.32	323762
Klungkung	ID		-8.53	115.40	223720
Knoxville	US	Tennessee	35.96	-83.92	190740
Knysna	ZA		-34.04	23.05	68659
Ko Samui	TH		9.54	99.94	50000
Kobe	JP		34.69	135.18	1525152
Koblenz	DE		50.35	7.58	107319
Kobo	ET		10.03	39.85	56100
Koboko	UG		3.41	30.96	64500
Kobryn	BY		52.21	24.36	52235
Koch Bihār	IN		26.33	89.45	78737
Koch'ang	KR		35.43	126.70	72996
Kochi	IN		9.94	76.26	633553
Kochi	JP		33.55	133.53	332059
Kodaira	JP		35.73	139.49	198739
Kodungallūr	IN		10.23	76.20	60190
Kodār	IN		17.00	79.97	64234
Koforidua	GH		6.09	-0.26	151255
Kofu	JP		35.67	138.57	189591
Koga	JP		36.18	139.72	139344
Koga	JP		33.73	130.47	58786
Kogalym	RU		62.27	74.48	57800
Koganei	JP		35.70	139.51	126074
Kogarah	AU		-33.97	151.14	16416
Kogon Shahri	UZ		39.73	64.55	62300
Kohat	PK		33.58	71.45	151427
Kohima	IN		25.67	94.11	99039
Koidu	SL		8.64	-10.97	128030
Kokomo	US	Indiana	40.49	-86.13	57995
Kokshetau	KZ		53.28	69.39	150649
Kokstad	ZA		-30.55	29.42	61751
Kokubu-matsuki	JP		31.73	130.77	57896
Kokubunji	JP		35.70	139.48	129242
Kolaboui	GN		10.80	-14.40	57251
Kolar	IN		23.16	77.42	87882
Kolda	SN		12.89	-14.94	103574
Kolding	DK		55.49	9.47	61638
Kolea	DZ		36.64	2.77	61643
Kolhāpur	IN		16.70	74.23	549236
Kolkata	IN		22.56	88.36	4631392
Kollam	IN		8.88	76.58	367107
Kollegāl	IN		12.15	77.11	57149
Kolomna	RU		55.07	38.78	147690
Kolomyia	UA		48.52	25.04	60821
Kolonnawa	LK		6.93	79.88	64887
Kolpino	RU		59.75	30.59	138979
Kolwezi	CD		-10.71	25.47	790248
Kolār	IN		13.14	78.13	138462
Kom Ombo	EG		24.48	32.95	409311
Komae	JP		35.63	139.58	84772
Komaki	JP		35.28	136.92	148872
Komatsu	JP		36.40	136.45	108509
Kombolcha	ET		11.08	39.74	132100
Komendantsky aerodrom	RU		60.00	30.28	84052
Komsomolsk-on-Amur	RU		50.55	137.01	275908
Kon Tum	VN		14.35	108.01	205762
Konak	TR		38.40	27.10	332277
Konan	JP		35.00	136.10	54607
Konch	IN		25.99	79.15	52773
Kondoa	TZ		-4.90	35.78	80443
Kongolo	CD		-5.39	27.00	86932
Kongoussi	BF		13.33	-1.53	53627
Konibodom	TJ		40.29	70.43	211100
Konin	PL		52.22	18.25	81258
Konnagar	IN		22.71	88.34	76082
Konotop	UA		51.23	33.20	84787
Konstanz	DE		47.66	9.18	81275
Kontagora	NG		10.40	5.47	98754
Konya	TR		37.87	32.48	1433861
Koolauloa	US	Hawaii	21.61	-157.93	15697
Kopargaon	IN		19.88	74.48	65273
Kopeysk	RU		55.12	61.62	70780
Koppal	IN		15.35	76.15	70698
Koratla	IN		18.82	78.71	66504
Korba	IN		22.35	82.70	419146
Korba	TN		36.58	10.86	65542
Koreatown	US	California	34.06	-118.30	124281
Korhogo	CI		9.46	-5.63	440926
Korla	CN		41.76	86.15	549324
Korogwe	TZ		-5.15	38.48	62032
Korolev	RU		55.91	37.83	139798
Korolyov	UA		50.24	28.70	114034
Koronadal	PH		6.50	124.85	201844
Korosten	UA		50.95	28.64	61496
Kortrijk	BE		50.83	3.26	73879
Korydallós	GR		37.98	23.65	63445
Korçë	AL		40.62	20.78	58259
Kosai	JP		34.70	137.52	59770
Koshigaya	JP		35.89	139.79	345353
Kosi	IN		27.79	77.44	52492
Koson	UZ		39.04	65.58	68900
Kosong	KR		38.38	128.47	62446
Kosonsoy	UZ		41.25	71.55	50900
Kostanay	KZ		53.21	63.62	210000
Kosti	SD		13.16	32.66	345068
Kostroma	RU		57.77	40.93	277280
Kostyantynivka	UA		48.53	37.71	67350
Koszalin	PL		54.19	16.17	107450
Kot Addu	PK		30.47	70.97	104217
Kot Kapūra	IN		30.58	74.83	91979
Kot Malik Barkhurdar	PK		30.20	66.99	69359
Kot Mumin	PK		32.19	73.03	51021
Kot Radha Kishan	PK		31.17	74.10	102057
Kota	IN		25.18	75.84	1001694
Kota Bharu	MY		6.12	102.24	568900
Kota Damansara	MY		3.15	101.58	500000
Kota Kinabalu	MY		5.97	116.07	500421
Kota Kuala Muda	MY		5.59	100.37	544984
Kota Sambas	ID		1.36	109.30	57295
Kota Tinggi	MY		1.74	103.90	52743
Kotamobagu	ID		0.74	124.31	121756
Kotharia	IN		22.23	70.82	53794
Kotido	UG		2.98	34.13	75700
Kotikawatta	LK		6.93	79.91	64565
Kotka	FI		60.47	26.95	50157
Kotkapura	IN		30.58	74.83	80741
Kotlas	RU		61.26	46.65	59180
Kotlovka	RU		55.66	37.60	64000
Kotri	PK		25.37	68.31	106615
Kottagūdem	IN		17.55	80.62	79819
Kottayam	IN		9.59	76.52	55374
Kotō	JP		32.78	130.75	543730
Koudougou	BF		12.25	-2.37	160239
Koulikoro	ML		12.86	-7.56	64128
Koumassi	CI		5.30	-3.97	412282
Koumra	TD		8.92	17.55	54109
Kousséri	CM		12.08	15.03	139024
Koutiala	ML		12.39	-5.47	218031
Kouvola	FI		60.87	26.70	78094
Kovel	UA		51.22	24.70	67575
Kovilpatti	IN		9.17	77.87	95057
Kovpakivskyi	UA		50.93	34.79	142447
Kovrov	RU		56.36	41.32	154224
Kowloon	HK		22.32	114.18	2232339
Kowloon City	HK		22.33	114.19	418732
Kowloon City Centre	HK		22.33	114.19	194290
Kowloon West End	HK		22.33	114.19	74710
Koyilandy	IN		11.44	75.69	71873
Kozan	TR		37.46	35.82	88115
Kozeyevo	RU		55.87	37.62	50000
Kozhikode	IN		11.25	75.78	550440
Kozhukhovo	RU		55.71	37.68	50000
Košice	SK		48.71	21.26	225044
Kpalimé	TG		6.90	0.63	75084
Kraaifontein	ZA		-33.85	18.72	57911
Kragujevac	RS		44.02	20.92	147473
Kraków	PL		50.06	19.94	816614
Kraljevo	RS		43.73	20.69	82846
Kramatorsk	UA		48.73	37.57	147145
Krasnaya Glinka	RU		53.74	52.94	85566
Krasnodar	RU		45.05	38.98	899541
Krasnogorsk	RU		55.82	37.33	92932
Krasnogvargeisky	RU		59.97	30.48	337091
Krasnokamensk	RU		50.09	118.03	54316
Krasnokamsk	RU		58.08	55.76	52689
Krasnoturinsk	RU		59.77	60.21	62600
Krasnoyarsk	RU		56.04	92.93	1090811
Krathum Baen	TH		13.65	100.26	72819
Krefeld	DE		51.34	6.55	237984
Kremenchuk	UA		49.06	33.40	224997
Kresek	ID		-6.13	106.38	110182
Kreuzberg	DE		52.50	13.40	153135
Kribi	CM		2.94	9.91	93482
Krishnagiri	IN		12.52	78.21	71323
Krishnanagar	IN		23.41	88.49	145926
Kristiansand	NO		58.15	8.00	117237
Kroonstad	ZA		-27.65	27.23	117152
Kropotkin	RU		45.44	40.57	79599
Kropyvnytskyi	UA		48.51	32.27	219676
Krugersdorp	ZA		-26.09	27.78	378821
Krujë	AL		41.51	19.79	51191
Kruševac	RS		43.58	21.33	75256
Krymsk	RU		44.93	37.99	57555
Kryukiv	UA		49.03	33.44	75578
Kryvyy Rih	UA		47.91	33.39	603904
Ksar	MR		18.10	-15.96	57758
Ksar Chellala	DZ		35.21	2.32	51451
Ksar el Boukhari	DZ		35.89	2.75	59634
Ksar El Kebir	MA		35.00	-5.90	138262
Ksar Hellal	TN		35.65	10.89	55415
Kstovo	RU		56.15	44.20	67242
Kuacjok	SS		8.30	27.98	78000
Kuala Krai	MY		5.53	102.20	105007
Kuala Kubu Baharu	MY		3.56	101.66	194387
Kuala Lumpur	MY		3.14	101.69	1453975
Kuala Nerus	MY		5.37	103.02	93485
Kuala Selangor	MY		3.35	101.25	55887
Kuala Terengganu	MY		5.33	103.14	426500
Kuandian	CN		40.73	124.78	70867
Kuantan	MY		3.81	103.33	548014
Kuchai Lama	MY		3.08	101.69	50000
Kuching	MY		1.55	110.33	402738
Kuchāman	IN		27.15	74.86	61969
Kudamatsu	JP		34.01	131.87	55887
Kudus	ID		-6.80	110.84	92156
Kufa	IQ		32.05	44.44	110000
Kuje	NG		8.88	7.23	97367
Kukatpally	IN		17.48	78.41	341709
Kukichūō	JP		36.07	139.67	150582
Kulai	MY		1.66	103.60	63762
Kulim	MY		5.36	100.56	170889
Kuliouou - Kalani Iki	US	Hawaii	21.30	-157.75	16195
Kulti	IN		23.73	86.84	305405
Kumagaya	JP		36.13	139.39	195277
Kumamoto	JP		32.81	130.69	738907
Kumanovo	MK		42.13	21.72	75051
Kumarapalayam	IN		11.44	77.71	195071
Kumasi	GH		6.69	-1.62	2544530
Kumba	CM		4.64	9.45	225046
Kumbakonam	IN		10.96	79.39	167155
Kumbo	CM		6.20	10.67	125124
Kumertau	RU		52.76	55.79	65321
Kuna	US	Idaho	43.49	-116.42	17226
Kundla	IN		21.34	71.31	76809
Kunduz	AF		36.73	68.86	161902
Kungsholmen	SE		59.33	18.04	69363
Kungur	RU		57.41	56.97	66389
Kuningan	ID		-6.98	108.48	111742
Kunitachi	JP		35.68	139.44	77130
Kuniyamuttūr	IN		10.96	76.95	95924
Kunjah	PK		32.53	73.97	90905
Kunming	CN		25.04	102.72	3855346
Kunnamkulam	IN		10.65	76.07	63903
Kunri	PK		25.18	69.57	237063
Kunshan	CN		31.38	120.95	2092496
Kuntsevo	RU		55.74	37.40	147497
Kunyang	CN		27.67	120.57	65009
Kuopio	FI		62.89	27.68	125462
Kupang	ID		-10.17	123.61	474801
Kupchino	RU		59.86	30.39	54198
Kurashiki	JP		34.58	133.77	483576
Kure	JP		34.23	132.57	214592
Kurgan	RU		55.45	65.34	309285
Kurichchi	IN		10.96	76.97	123667
Kurihama	JP		35.23	139.70	53782
Kurihara	JP		38.75	141.00	66565
Kurnool	IN		15.83	78.04	460184
Kuroiso	JP		36.97	140.05	61230
Kurortnyy	RU		60.17	29.91	70589
Kursk	RU		51.73	36.18	448733
Kurume	JP		33.32	130.52	303579
Kusatsu	JP		35.02	135.97	143913
Kushinagar	IN		26.74	83.89	274403
Kushiro	JP		42.98	144.37	167875
Kushtia	BD		23.90	89.12	135724
Kutaisi	GE		42.27	42.69	135201
Kutloanong	ZA		-27.83	26.75	95008
Kutu	CD		-2.72	18.15	56061
Kuwait City	KW		29.37	47.97	60064
Kuwana	JP		35.05	136.67	140051
Kuznetsk	RU		53.12	46.60	90480
Kuz’minki	RU		55.70	37.80	143000
Kuşadası	TR		37.86	27.26	63177
KwaDukuza	ZA		-29.33	31.29	161177
Kwaggafontein	ZA		-25.33	28.94	54040
Kwai Chung	HK		22.37	114.14	331600
Kwail-ŭp	KP		38.45	125.02	89895
Kwangyang	KR		34.98	127.59	89281
Kwekwe	ZW		-18.93	29.81	119863
Kwinana	AU		-32.23	115.78	30433
Kyaiklat	MM		16.45	95.72	52425
Kyaukpyu	MM		19.43	93.55	180000
Kyaukse	MM		21.61	96.14	50480
Kyauktan	MM		16.64	96.33	132765
Kyengera	UG		0.30	32.50	285400
Kyimyindine	MM		16.81	96.12	111514
Kyiv	UA		50.45	30.52	2952301
Kyivskyi	UA		48.05	37.78	139177
Kyivskyi	UA		49.61	34.53	110600
Kyle	US	Texas	29.99	-97.88	35733
Kyosai	KR		34.85	128.59	72124
Kyoto	JP		35.02	135.75	1463723
Kyzyl	RU		51.71	94.44	116983
Kyzylorda	KZ		44.85	65.51	354800
Kyōtanabe	JP		34.80	135.77	73753
Kyōtango	JP		35.61	135.04	50860
Kâhta	TR		37.79	38.62	97875
Kélibia	TN		36.85	11.09	62993
Kérou	BJ		10.83	2.10	54276
Köln	DE		50.93	6.95	1024621
Köpenick	DE		52.45	13.57	67148
Körfez	TR		40.77	29.78	90580
Kütahya	TR		39.42	29.98	185008
Küçükçekmece	TR		40.99	28.77	792030
Kākināda	IN		16.96	82.24	384182
Kāliyāganj	IN		25.63	88.33	51748
Kālna	IN		23.22	88.36	53964
Kāmthi	IN		21.22	79.20	86793
Kāmyārān	IR		34.80	46.94	57077
Kāmāreddi	IN		18.32	78.34	80315
Kāmārhāti	IN		22.67	88.37	332965
Kānchrāpāra	IN		22.96	88.43	136954
Kāndi	IN		23.96	88.04	54848
Kāpas Herd	IN		28.53	77.08	74073
Kāraikkudi	IN		10.07	78.77	181851
Kāraikāl	IN		10.92	79.83	86838
Kāranja	IN		20.48	77.49	67907
Kāsaragod	IN		12.50	74.99	54172
Kāsganj	IN		27.81	78.65	99462
Kāshmar	IR		35.24	58.47	131517
Kāshān	IR		34.00	51.44	304487
Kāsipālaiyam	IN		11.32	77.71	73425
Kāsībugga	IN		18.76	84.42	57507
Kātoya	IN		23.65	88.13	78408
Kātrās	IN		23.80	86.30	57349
Kāvali	IN		14.92	79.99	90099
Kāzerūn	IR		29.62	51.65	112360
Kēng Tung	MM		21.63	99.93	171620
Kędzierzyn-Koźle	PL		50.35	18.23	65636
Kīhei	US	Hawaii	20.76	-156.45	20881
Kīratpur	IN		29.51	78.21	60223
Kırklareli	TR		41.74	27.23	58223
Kırıkhan	TR		36.50	36.36	60916
Kırıkkale	TR		39.85	33.51	186960
Kırşehir	TR		39.15	34.16	150700
Kızıltepe	TR		37.19	40.58	150174
Kōka	JP		34.98	136.16	89619
Kōnan	JP		35.33	136.87	98255
Kōnosu	JP		36.07	139.52	116828
Kōriyama	JP		37.40	140.38	327692
Kōshi	JP		32.89	130.78	61772
Kōtari	JP		34.92	135.71	80608
Kőbánya	HU		47.48	19.14	78414
Kūhdasht	IR		33.53	47.61	89091
Kūt-e ‘Abdollāh	IR		31.24	48.66	56252
Kŭlob	TJ		37.91	69.78	214700
Kỳ Anh	VN		18.06	106.30	150226
K’olīto	ET		7.32	38.08	72200
L'Amoreaux	CA		43.80	-79.31	43993
L'Ancienne-Lorette	CA		46.79	-71.35	16516
L'Assomption	CA		45.82	-73.43	15906
L'Hospitalet de Llobregat	ES		41.36	2.10	257038
L'Île-Bizard–Sainte-Geneviève	CA		45.49	-73.90	19857
La Calera	CL		-32.79	-71.20	50221
La Carlota	PH		10.42	122.92	67740
La Cañada Flintridge	US	California	34.20	-118.19	20246
La Ceiba	HN		15.76	-86.78	222055
La Ceiba	HN		15.77	-86.83	215973
La Chorrera	PA		8.88	-79.78	61232
La Cité-Limoilou	CA		46.83	-71.23	108415
La Concepción	VE		10.62	-71.84	120478
La Crescenta-Montrose	US	California	34.23	-118.24	19653
La Crosse	US	Wisconsin	43.80	-91.24	52306
La Dolorita	VE		10.49	-66.79	56846
La Dorada	CO		5.45	-74.66	81950
La Fría	VE		8.22	-72.25	61568
La Gazelle	TN		36.89	10.19	94961
La Gi	VN		10.66	107.77	160652
La Grange	US	Illinois	41.81	-87.87	15723
La Habana Vieja	CU		23.13	-82.35	95383
La Habra	US	California	33.93	-117.95	62131
La Haute-Saint-Charles	CA		46.89	-71.37	88460
La Jolla	US	California	32.85	-117.27	42808
La Laguna	ES		28.49	-16.32	150661
La Libertad	EC		-2.23	-80.91	75881
La Louvière	BE		50.49	4.19	76668
La Línea de la Concepción	ES		36.17	-5.35	64595
La Marque	US	Texas	29.37	-94.97	15908
La Marsa	TN		36.88	10.32	92987
La Mesa	US	California	32.77	-117.02	60089
La Mirada	US	California	33.92	-118.01	49520
La Mohammedia	TN		36.67	10.16	66593
la Nova Esquerra de l'Eixample	ES		41.38	2.15	57676
La Palma	US	California	33.85	-118.05	15904
La Paz	BO		-16.50	-68.15	2004652
La Paz	MX		24.14	-110.31	250141
La Paz	PH		15.44	120.73	71978
La Piedad de Cabadas	MX		20.34	-102.02	83323
La Pintana	CL		-33.58	-70.63	201178
La Plata	AR		-34.92	-57.95	195443
La Porte	US	Texas	29.67	-95.02	35148
La Porte	US	Indiana	41.61	-86.71	21916
La Prairie	CA		45.42	-73.50	23357
La Presa	US	California	32.71	-117.00	34169
La Puente	US	California	34.02	-117.95	40745
La Quinta	US	California	33.66	-116.31	40476
La Rioja	AR		-29.41	-66.86	178872
La Roche-sur-Yon	FR		46.67	-1.43	59410
La Rochelle	FR		46.16	-1.15	76810
La Romana	DO		18.42	-68.97	208437
La Serena	CL		-29.91	-71.25	154521
La Seyne-sur-Mer	FR		43.10	5.88	62330
La Spezia	IT		44.10	9.82	93288
La Trinidad	PH		16.45	120.59	142925
La Vega	DO		19.22	-70.53	102426
La Vergne	US	Tennessee	36.02	-86.58	34794
La Verne	US	California	34.10	-117.77	32681
La Victoria	VE		10.23	-67.33	126721
la Vila de Gràcia	ES		41.40	2.16	50928
La Villa del Rosario	VE		10.33	-72.31	82766
La Vista	US	Nebraska	41.18	-96.03	16921
Laascaanood	SO		8.48	47.36	60100
Laayoune	EH		27.14	-13.19	196331
Labinsk	RU		44.64	40.74	61945
Labrador	AU		-27.94	153.40	18326
Labuan	MY		5.28	115.25	95120
Labuan Bajo	ID		-8.50	119.89	188724
Labé	GN		11.32	-12.28	107571
Lacey	US	Washington	47.03	-122.82	46409
Lackawanna	US	New York	42.83	-78.82	17965
Laconia	US	New Hampshire	43.53	-71.47	16227
Ladera Ranch	US	California	33.57	-117.64	22980
Ladner	CA		49.09	-123.08	23016
Ladysmith	ZA		-28.56	29.78	143446
Lae	PG		-6.72	147.00	76255
Lafayette	US	Louisiana	30.22	-92.02	121374
Lafayette	US	Indiana	40.42	-86.88	71111
Lafayette	US	Colorado	39.99	-105.09	27729
Lafayette	US	California	37.89	-122.12	25843
Lafia	NG		8.49	8.52	127236
Lafiagi	NG		8.85	5.42	102779
Laflèche	CA		45.50	-73.47	17499
Lagarto	BR		-10.92	-37.65	101579
Lages	BR		-27.82	-50.33	164676
Laghouat	DZ		33.80	2.87	134372
Lagoa da Prata	BR		-20.02	-45.54	51412
Lagoa Santa	BR		-19.63	-43.90	75145
Lagos	NG		6.45	3.39	15388000
Lagos de Moreno	MX		21.36	-101.93	98206
LaGrange	US	Georgia	33.04	-85.03	29588
Laguna	US	California	38.42	-121.42	46621
Laguna Beach	US	California	33.54	-117.78	23365
Laguna Hills	US	California	33.61	-117.71	31748
Laguna Niguel	US	California	33.52	-117.71	65806
Laguna Woods	US	California	33.61	-117.73	16406
Lahad Datu	MY		5.02	118.33	105622
Lahat	ID		-3.79	103.54	65906
Lahbab	AE		25.04	55.59	53079
Lahore	PK		31.56	74.35	13004135
Lahr	DE		48.34	7.87	50775
Lahraouyine	MA		33.54	-7.53	70783
Lahti	FI		60.98	25.66	121622
Lahān	NP		26.72	86.48	102955
Lai Vung	VN		10.26	105.59	80649
Laibin	CN		23.75	109.22	910282
Laiwu	CN		36.19	117.66	989535
Laixi	CN		36.86	120.53	341470
Laiyang	CN		36.98	120.71	169594
Laizhou	CN		37.18	119.94	188000
Lajeado	BR		-23.53	-46.41	164391
Lajeado	BR		-29.47	-51.96	93646
Lak Si	TH		13.89	100.58	109770
Lakang	MM		24.66	97.19	85423
Lake Butler	US	Florida	28.50	-81.54	15400
Lake Charles	US	Louisiana	30.21	-93.20	76070
Lake Country	CA		50.01	-119.40	15817
Lake Elsinore	US	California	33.67	-117.33	61981
Lake Forest	US	California	33.65	-117.69	82492
Lake Forest	US	Illinois	42.26	-87.84	19408
Lake Havasu City	US	Arizona	34.48	-114.32	53553
Lake in the Hills	US	Illinois	42.18	-88.33	29024
Lake Jackson	US	Texas	29.03	-95.43	27533
Lake Magdalene	US	Florida	28.07	-82.47	28509
Lake Mary	US	Florida	28.76	-81.32	16021
Lake Oswego	US	Oregon	45.42	-122.67	38496
Lake Ridge	US	Virginia	38.69	-77.30	41058
Lake Ronkonkoma	US	New York	40.84	-73.13	20155
Lake Shore	US	Maryland	39.11	-76.48	19477
Lake Stevens	US	Washington	48.02	-122.06	30886
Lake Wales	US	Florida	27.90	-81.59	15541
Lake Worth Beach	US	Florida	26.62	-80.07	37498
Lake Worth Corridor	US	Florida	26.62	-80.10	20635
Lake Zurich	US	Illinois	42.20	-88.09	19993
Lakeland	US	Florida	28.04	-81.95	104401
Lakemba	AU		-33.92	151.08	16921
Lakeside	US	Florida	30.13	-81.77	30943
Lakeside	US	California	32.86	-116.92	20648
Lakeville	US	Minnesota	44.65	-93.24	60633
Lakewood	US	Colorado	39.70	-105.08	152597
Lakewood	US	California	33.85	-118.13	81611
Lakewood	US	Washington	47.17	-122.52	59829
Lakewood	US	New Jersey	40.10	-74.22	53805
Lakewood	CA		52.11	-106.59	51237
Lakewood	US	Ohio	41.48	-81.80	50656
Lakhīmpur	IN		27.95	80.78	140223
Lakshmīpur	BD		22.94	90.83	61703
Lal Bahadur Nagar	IN		17.35	78.56	261987
Lala Musa	PK		32.70	73.96	65197
Lalian	PK		31.82	72.80	52542
Lalitpur	IN		24.69	78.42	126475
Lalmonirhat	BD		25.92	89.45	65127
Lalor	AU		-37.67	145.02	23219
Lalupon	NG		7.47	4.07	81130
Lambaré	PY		-25.35	-57.61	126377
Lambayong	PH		6.52	125.04	81288
Lamezia Terme	IT		38.96	16.31	70501
Lamongan	ID		-7.12	112.42	59224
Lamont	US	California	35.26	-118.91	15120
Lampa	CL		-33.29	-70.88	102234
Lampang	TH		18.29	99.49	156139
Lamía	GR		38.90	22.43	52006
Lancaster	US	California	34.70	-118.14	161103
Lancaster	US	Pennsylvania	40.04	-76.31	59339
Lancaster	GB		54.05	-2.80	47162
Lancaster	US	Ohio	39.71	-82.60	39766
Lancaster	US	Texas	32.59	-96.76	38801
Lancing	GB		50.83	-0.32	18692
Land O' Lakes	US	Florida	28.22	-82.46	31996
Lander	VE		10.18	-66.70	176346
Landover	US	Maryland	38.93	-76.90	23078
Landsdale	AU		-31.81	115.87	15401
Landshut	DE		48.53	12.16	71863
Landstraße	AT		48.20	16.39	98389
Lang'ata	KE		-1.37	36.73	172569
Langarūd	IR		37.20	50.15	68148
Langenfeld	DE		51.11	6.95	59112
Langenhagen	DE		52.45	9.74	50439
Langfang	CN		39.52	116.71	868066
Langford	CA		48.45	-123.50	46584
Langley	CA		49.10	-122.66	132603
Langley Park	US	Maryland	38.99	-76.98	18755
Langsa	ID		4.47	97.97	184016
Langtoucun	CN		40.04	124.34	59046
Langwarrin	AU		-38.17	145.17	22146
Langxiang	CN		46.95	128.87	57318
Langzhong	CN		31.55	105.99	60542
Lanham-Seabrook	US	Maryland	38.97	-76.85	18190
Lankaran	AZ		38.75	48.85	89300
Lansdale	US	Pennsylvania	40.24	-75.28	16512
Lanshan	CN		33.94	117.72	55442
Lansing	US	Michigan	42.73	-84.56	112644
Lansing	US	Illinois	41.56	-87.54	28349
Lansing-Westgate	CA		43.75	-79.42	16164
Lanxi	CN		29.22	119.47	73706
Lanxi	CN		46.26	126.28	72528
Lanzhou	CN		36.06	103.84	3000000
Lanús	AR		-34.71	-58.39	212252
Laoag	PH		18.20	120.60	112117
Laohekou	CN		32.39	111.67	253112
Laojunmiao	CN		39.83	97.73	84769
Lapa	BR		-23.52	-46.71	75533
Laplace	US	Louisiana	30.07	-90.48	29872
Lappeenranta	FI		61.06	28.19	72909
Lapu-Lapu City	PH		10.31	123.95	497813
Lara	AU		-38.02	144.41	15919
Larache	MA		35.19	-6.16	136505
Laramie	US	Wyoming	41.31	-105.59	32158
Larbaâ	DZ		36.56	3.15	58295
Laredo	US	Texas	27.51	-99.51	256153
Largo	US	Florida	27.91	-82.79	81000
Larkana	PK		27.56	68.21	364033
Larkhall	GB		55.73	-3.97	15030
Larnaca	CY		34.92	33.63	72000
Larne	GB		54.85	-5.82	18421
Las Cruces	US	New Mexico	32.31	-106.78	101643
Las Cumbres	PA		9.09	-79.54	69102
Las Palmas de Gran Canaria	ES		28.10	-15.42	383516
Las Piedras	UY		-34.73	-56.22	69682
Las Piñas	PH		14.45	120.98	615549
Las Rozas de Madrid	ES		40.49	-3.87	95550
Las Tunas	CU		20.96	-76.95	203684
Las Vegas	US	Nevada	36.17	-115.14	641903
Las Águilas	ES		40.38	-3.77	51268
LaSalle	CA		42.24	-83.06	32721
Lashio	MM		22.94	97.75	131000
Lasnamäe	EE		59.43	24.86	115008
Lat Krabang	TH		13.72	100.78	163175
Lat Phrao	TH		13.80	100.61	122182
Latacunga	EC		-0.93	-78.62	205624
Latakia	SY		35.53	35.79	709000
Latchmere	GB		51.47	-0.17	15358
Latham	US	New York	42.75	-73.76	20736
Lathrop	US	California	37.82	-121.28	20866
Latina	ES		40.39	-3.75	256644
Latina	IT		41.47	12.90	76305
Latkrabang	TH		13.73	100.75	173987
Latur	IN		18.40	76.57	382940
Lauderdale Lakes	US	Florida	26.17	-80.21	34796
Lauderhill	US	Florida	26.14	-80.21	71579
Launceston	AU		-41.44	147.13	90953
Laurel	US	Maryland	39.10	-76.85	26215
Laurel	US	Mississippi	31.69	-89.13	18837
Laurel	US	Virginia	37.64	-77.51	16713
Laurelton	US	New York	40.67	-73.75	21053
Laurinburg	US	North Carolina	34.77	-79.46	15507
Lauro de Freitas	BR		-12.89	-38.33	203331
Lausanne	CH		46.52	6.63	139111
Lautoka	FJ		-17.62	177.45	52500
Laval	CA		45.57	-73.69	438366
Laval	FR		48.07	-0.77	50489
Laval-des-Rapides	CA		45.56	-73.70	36933
Lavras	BR		-21.25	-45.00	104761
Lawang	ID		-7.84	112.69	112540
Lawndale	US	California	33.89	-118.35	33430
Lawndale	US	Pennsylvania	40.05	-75.09	24134
Lawrence	US	Kansas	38.97	-95.24	93917
Lawrence	US	Massachusetts	42.71	-71.16	80231
Lawrence	US	Indiana	39.84	-86.03	47809
Lawrence Park South	CA		43.72	-79.41	15179
Lawrenceville	US	Georgia	33.96	-83.99	30493
Lawson	CA		52.16	-106.64	34620
Lawton	US	Oklahoma	34.61	-98.39	96655
Laxmangarh	IN		27.82	75.03	53392
Layton	US	Utah	41.06	-111.97	74143
Layyah	PK		30.96	70.94	151274
Le Bardo	TN		36.81	10.13	71961
Le Havre	FR		49.49	0.11	185972
Le Kram	TN		36.84	10.32	88302
Le Mans	FR		48.00	0.20	144515
Le Plateau-Mont-Royal	CA		45.53	-73.58	105813
Le Sud-Ouest	CA		45.47	-73.59	86347
Le Tampon	RE		-21.28	55.52	81943
Le Vieux-Longueuil	CA		45.54	-73.51	135218
League City	US	Texas	29.51	-95.09	98312
Lealman	US	Florida	27.82	-82.68	19879
Leamington	CA		42.05	-82.60	35730
Leander	US	Texas	30.58	-97.85	59202
Leaside-Bennington	CA		43.70	-79.37	16828
Leatherhead	GB		51.30	-0.33	43544
Leavenworth	US	Kansas	39.31	-94.92	35980
Leawood	US	Kansas	38.97	-94.62	34579
Lebanon	US	Tennessee	36.21	-86.29	30262
Lebanon	US	Pennsylvania	40.34	-76.41	25534
Lebanon	US	Ohio	39.44	-84.20	20623
Lebanon	US	Oregon	44.54	-122.91	16324
Lebanon	US	Indiana	40.05	-86.47	15892
Lecce	IT		40.35	18.17	80695
Lecheng	CN		25.13	113.35	124268
Leduc	CA		53.27	-113.55	15561
Ledyard	US	Connecticut	41.44	-72.01	15212
Lee's Summit	US	Missouri	38.91	-94.38	95094
Leeds	GB		53.80	-1.55	536280
Leek	GB		53.10	-2.02	19385
Leesburg	US	Virginia	39.12	-77.56	51209
Leesburg	US	Florida	28.81	-81.88	21993
Leeuwarden	NL		53.20	5.81	124481
Lefortovo	RU		55.77	37.70	91000
Leganés	ES		40.33	-3.76	188425
Legaspi	PH		13.14	123.74	179481
Legionowo	PL		52.40	20.93	50786
Legnano	IT		45.60	8.92	57589
Legnica	PL		51.21	16.16	106033
Lehi	US	Utah	40.39	-111.85	58486
Lehigh Acres	US	Florida	26.63	-81.62	86784
Leicester	GB		52.64	-1.13	368600
Leiden	NL		52.16	4.49	119713
Leigh	GB		53.50	-2.52	43626
Leighton Buzzard	GB		51.92	-0.66	42727
Leipzig	DE		51.34	12.37	504971
Leiria	PT		39.74	-8.81	128640
Leisure City	US	Florida	25.50	-80.43	26324
Leixlip	IE		53.37	-6.50	15504
Leiyang	CN		26.40	112.86	129116
Lekki	NG		6.45	3.48	401272
Leland	US	North Carolina	34.26	-78.04	17924
Lelystad	NL		52.51	5.47	79811
Lemay	US	Missouri	38.53	-90.28	16645
Lembang	ID		-6.81	107.62	183130
Leme	BR		-22.19	-47.39	98161
Lemon Grove	US	California	32.74	-117.03	26709
Lemont	US	Illinois	41.67	-88.00	16788
Lemoore	US	California	36.30	-119.78	25647
Lenexa	US	Kansas	38.95	-94.73	52490
Lengshuijiang	CN		27.69	111.43	115399
Lengshuitan	CN		26.41	111.60	88935
Leninogorsk	RU		54.60	52.45	66263
Leninsk-Kuznetsky	RU		54.66	86.17	109023
Lennox	US	California	33.94	-118.35	22753
Lenoir	US	North Carolina	35.91	-81.54	17888
Lents	US	Oregon	45.48	-122.57	20156
Lençóis Paulista	BR		-22.60	-48.80	66505
Leominster	US	Massachusetts	42.53	-71.76	41569
Leopoldina	BR		-21.53	-42.64	51145
Lerdo	MX		25.54	-103.52	79669
Lere	NG		10.39	8.57	93290
Lerik	AZ		38.77	48.41	87000
Les Abymes	GP		16.27	-61.51	53514
Les Cayes	HT		18.19	-73.75	125799
Les Corts	ES		41.39	2.13	82270
Les Coteaux	CA		45.28	-74.23	17396
Les Rivières	CA		46.82	-71.27	77000
Leshan	CN		29.56	103.76	662814
Leskovac	RS		43.00	21.95	94758
Lesnoy	RU		57.62	63.08	55100
Lesosibirsk	RU		58.24	92.48	65945
Leszno	PL		51.84	16.57	63565
Letchworth Garden City	GB		51.98	-0.23	33990
Lethbridge	CA		49.70	-112.82	103197
Letterkenny	IE		54.95	-7.73	22549
Leuven	BE		50.88	4.70	101032
Levallois-Perret	FR		48.89	2.29	62178
Leverkusen	DE		51.03	6.98	162738
Levin	NZ		-40.63	175.28	19789
Levittown	US	Pennsylvania	40.16	-74.83	52983
Levittown	US	New York	40.73	-73.51	51881
Levoberezhnyy	RU		55.86	37.47	52000
Lewes	GB		50.87	0.01	17297
Lewiston	US	Maine	44.10	-70.21	36202
Lewiston	US	Idaho	46.42	-117.02	32544
Lewiston Orchards	US	Idaho	46.38	-116.98	31422
Lewisville	US	Texas	33.05	-96.99	104039
Lexington	US	Kentucky	37.99	-84.48	320347
Lexington	US	Massachusetts	42.45	-71.22	31394
Lexington	US	South Carolina	33.98	-81.24	20138
Lexington	US	North Carolina	35.82	-80.25	19326
Lexington-Fayette	US	Kentucky	38.05	-84.46	314488
Leyland	GB		53.70	-2.69	37614
Leytonstone	GB		51.57	0.01	54696
León	NI		12.44	-86.88	144538
León	ES		42.60	-5.57	124772
León de los Aldama	MX		21.12	-101.68	1579803
Lhasa	CN		29.65	91.10	118721
Lhoka	CN		29.24	91.77	353700
Lhokseumawe	ID		5.18	97.15	200876
Lhünzhub	CN		29.89	91.26	50596
Liancheng	CN		25.72	116.75	60504
Lianghu	CN		29.99	120.90	155000
Liangji	CN		33.96	117.97	52048
Liangping	CN		30.66	107.77	137620
Liangxiang	CN		39.74	116.13	76744
Liangzhai	CN		34.50	116.75	54742
Lianhe	CN		47.13	129.27	121367
Lianjiang	CN		21.65	110.28	100341
Lianozovo	RU		55.90	37.59	86000
Lianshan	CN		40.76	120.85	313247
Lianyuan	CN		27.69	111.66	66501
Lianyungang	CN		34.60	119.22	2001009
Lianzhou	CN		24.78	112.37	92827
Liaocheng	CN		36.45	116.00	1229768
Liaolan	CN		36.67	119.88	84306
Liaoyang	CN		41.27	123.17	687890
Liaozhong	CN		41.51	122.72	54691
Liberal	US	Kansas	37.04	-100.92	20746
Liberdade	BR		-23.56	-46.63	66056
Liberec	CZ		50.77	15.06	102951
Libertad	PH		8.94	125.50	250353
Liberty	US	Missouri	39.25	-94.42	30450
Libertyville	US	Illinois	42.28	-87.95	20436
Libon	PH		13.30	123.44	68846
Libreville	GA		0.39	9.45	846090
Licha	CN		36.06	119.78	55140
Licheng	CN		23.30	113.82	172775
Licheng	CN		31.43	119.48	72276
Lichfield	GB		52.68	-1.83	34738
Lichinga	MZ		-13.31	35.24	281341
Lichtenburg	ZA		-26.15	26.16	65863
Lichtenrade	DE		52.40	13.41	52110
Lichterfelde	DE		52.43	13.31	85885
Lichuan	CN		30.30	108.85	120587
Lida	BY		53.88	25.30	103262
Lidcombe	AU		-33.86	151.04	19791
Lido di Ostia	IT		41.73	12.28	85301
Lidu	CN		29.74	107.29	88124
Liepāja	LV		56.50	21.01	67421
Ligezhuang	CN		36.36	120.14	65714
Liguo	CN		34.55	117.33	54960
Lijiang	CN		26.87	100.22	211151
Likasi	CD		-10.98	26.74	635768
Likhobory	RU		55.85	37.57	50000
Liliha - Kapalama	US	Hawaii	21.34	-157.85	24953
Lille	FR		50.63	3.06	238695
Lillestrøm	NO		59.96	11.05	89684
Lilongwe	MW		-13.97	33.79	1115815
Lilydale	AU		-37.75	145.35	17348
Lima	PE		-12.04	-77.03	7737002
Lima	US	Ohio	40.74	-84.11	37873
Limassol	CY		34.68	33.04	154000
Limay	PH		14.56	120.60	81960
Limbe	CM		4.02	9.21	131381
Limehouse	GB		51.51	-0.03	15986
Limeira	BR		-22.56	-47.40	291869
Limerick	IE		52.66	-8.62	102287
Limerick	US	Pennsylvania	40.23	-75.52	18074
Limoeiro	BR		-7.87	-35.45	56510
Limoeiro do Norte	BR		-5.15	-38.10	59560
Limoges	FR		45.83	1.25	141176
Limpio	PY		-25.17	-57.49	96143
Limuru	KE		-1.11	36.64	159314
Limão	BR		-23.49	-46.67	82373
Limón	CR		9.99	-83.04	63081
Linares	MX		24.86	-99.57	70378
Linares	CL		-35.85	-71.59	69535
Linares	ES		38.10	-3.64	57414
Lincang	CN		23.88	100.09	323708
Lincoln	US	Nebraska	40.80	-96.67	294757
Lincoln	GB		53.23	-0.54	103813
Lincoln	US	California	38.89	-121.29	49757
Lincoln	US	Rhode Island	41.92	-71.44	21670
Lincoln	NZ		-36.86	174.62	17240
Lincoln Park	US	Illinois	41.92	-87.65	66959
Lincoln Park	US	Michigan	42.25	-83.18	37012
Lincoln Square	US	Illinois	41.98	-87.69	40761
Lincolnia	US	Virginia	38.82	-77.14	22855
Linda	US	California	39.13	-121.55	17773
Linden	US	New Jersey	40.62	-74.24	42021
Lindenhurst	US	New York	40.69	-73.37	27277
Lindenwold	US	New Jersey	39.82	-75.00	17613
Lindi	TZ		-10.00	39.72	95096
Lindsay	CA		44.35	-78.73	20354
Linfen	CN		36.09	111.52	959198
Lingao	CN		19.91	109.69	64874
Lingayen	PH		16.02	120.23	56580
Lingcheng	CN		33.82	118.11	53841
Lingdong	CN		46.55	131.14	83636
Lingen	DE		52.52	7.33	51310
Linghai	CN		41.17	121.37	56176
Linghe	CN		36.36	119.08	99069
Lingwu	CN		38.10	106.34	52863
Lingyuan	CN		41.24	119.40	91418
Linh Đàm	VN		20.96	105.83	70000
Linhares	BR		-19.39	-40.07	166786
Linjiacun	CN		35.99	119.65	88509
Linjiang	CN		31.10	108.22	71149
Linjiang	CN		41.81	126.91	69149
Linkou	CN		45.28	130.27	77754
Linköping	SE		58.41	15.62	166673
Lino Lakes	US	Minnesota	45.16	-93.09	21050
Linping	CN		30.42	120.30	78180
Linqiong	CN		30.42	103.46	55587
Linqu	CN		36.52	118.54	299646
Lins	BR		-21.68	-49.74	78503
Linshui	CN		36.42	114.20	109955
Linton Hall	US	Virginia	38.76	-77.57	35725
Lintong	CN		34.38	109.21	75882
Linxi	CN		39.71	118.45	100316
Linxia Chengguanzhen	CN		35.60	103.21	274466
Linyi	CN		35.06	118.34	2743843
Linz	AT		48.31	14.29	204846
Lipa City	PH		13.94	121.16	212287
Lipetsk	RU		52.59	39.55	509735
Liping	CN		26.23	109.13	82710
Lippstadt	DE		51.67	8.34	67219
Lira	UG		2.25	32.90	119323
Lisala	CD		2.15	21.52	117464
Lisbon	PT		38.73	-9.15	517802
Lisburn	GB		54.52	-6.04	77506
Lishi	CN		29.08	106.26	66620
Lishu	CN		43.31	124.33	61584
Lishui	CN		28.46	119.91	451418
Liski	RU		50.98	39.50	55939
Lisle	US	Illinois	41.80	-88.07	22964
Lisovyi Masyv	UA		50.47	30.63	87300
Litherland	GB		53.47	-3.00	22971
Lithia Springs	US	Georgia	33.79	-84.66	15491
Little Elm	US	Texas	33.16	-96.94	38341
Little Havana	US	Florida	25.77	-80.23	53430
Little Portugal	CA		43.65	-79.43	15559
Little Rock	US	Arkansas	34.75	-92.29	202591
Littlehampton	GB		50.81	-0.54	58714
Littleton	US	Colorado	39.61	-105.02	46368
Liuhe	CN		42.28	125.75	66975
Liuji	CN		34.36	117.05	54785
Liuku	CN		25.85	98.86	63013
Liupanshui	CN		26.59	104.83	1320825
Liuquan	CN		34.43	117.30	51657
Liuxin	CN		34.37	117.11	65258
Liuzhi	CN		26.23	105.43	138826
Liuzhou	CN		24.32	109.41	1436599
Live Oak	US	California	36.98	-121.98	17158
Live Oak	US	Texas	29.57	-98.34	15346
Livermore	US	California	37.68	-121.77	88126
Liverpool	GB		53.41	-2.98	496770
Liverpool	AU		-33.92	150.93	31078
Liversedge	GB		53.71	-1.69	19420
Livingston	GB		55.90	-3.52	56840
Livingston	US	New Jersey	40.80	-74.31	27853
Livingstone	ZM		-17.84	25.85	178361
Livoberezhnyi	UA		47.11	37.64	122175
Livonia	US	Michigan	42.37	-83.35	94635
Livorno	IT		43.54	10.33	157017
Lixian	CN		34.19	105.17	58300
Lizhi	CN		29.70	107.40	156753
Liège	BE		50.63	5.57	195278
Ljubljana	SI		46.05	14.51	272220
Llandudno	GB		53.32	-3.83	15371
Llanelli	GB		51.68	-4.16	49591
Lleida	ES		41.62	0.62	140797
Lloydminster	CA		53.27	-110.02	31582
Lo Prado	CL		-33.44	-70.73	104316
Loa Janan	ID		-0.58	117.10	212816
Lobito	AO		-12.36	13.54	393079
Lobnya	RU		56.03	37.47	61772
Lochearn	US	Maryland	39.34	-76.72	25333
Lockport	US	Illinois	41.59	-88.06	25175
Lockport	US	New York	43.17	-78.69	20624
Lod	IL		31.95	34.89	77223
Lodhran	PK		29.53	71.63	144512
Lodi	US	California	38.13	-121.27	64596
Lodi	US	New Jersey	40.88	-74.08	24835
Lodja	CD		-3.52	23.60	91409
Lodwar	KE		3.12	35.60	82970
Lofthouse	GB		53.73	-1.50	23458
Logan	US	Utah	41.74	-111.83	50371
Logan	US	Pennsylvania	40.03	-75.15	21926
Logan City	AU		-27.64	153.11	345098
Logan Square	US	Illinois	41.92	-87.70	73702
Logansport	US	Indiana	40.75	-86.36	17793
Logroño	ES		42.47	-2.45	151164
LOHAS Park	HK		22.29	114.27	50000
Lohārdagā	IN		23.43	84.68	57411
Loja	EC		-3.99	-79.20	274112
Lokoja	NG		7.80	6.74	60579
Loma Linda	US	California	34.05	-117.26	24045
Lomas de Zamora	AR		-34.76	-58.40	111897
Lombard	US	Illinois	41.88	-88.01	43797
Lomita	US	California	33.79	-118.32	20785
Lompoc	US	California	34.64	-120.46	44164
Lomé	TG		6.13	1.22	2188376
Lonavla	IN		18.75	73.41	58562
London	GB		51.51	-0.13	8961989
London	CA		42.98	-81.23	422324
Londonderry County Borough	GB		55.00	-7.31	87153
Londrina	BR		-23.31	-51.16	581382
Long Beach	US	California	33.77	-118.19	474140
Long Beach	US	New York	40.59	-73.66	33550
Long Beach	US	Mississippi	30.35	-89.15	15555
Long Bien	VN		21.03	105.90	347829
Long Branch	US	New Jersey	40.30	-73.99	30941
Long Eaton	GB		52.90	-1.27	47898
Long Island City	US	New York	40.74	-73.95	25595
Long Khánh	VN		10.93	107.25	171276
Long Mỹ	VN		9.68	105.57	61781
Long Xuyên	VN		10.39	105.44	286140
Longfellow Community	US	Minnesota	44.94	-93.23	29295
Longfeng	CN		46.53	125.10	152074
Longfeng	CN		30.39	109.51	61862
Longfield	GB		51.40	0.30	16808
Longgang	CN		22.72	114.26	215273
Longgang	CN		29.70	105.71	74605
Longgang	CN		37.65	120.33	60444
Longgu	CN		34.90	116.81	59086
Longjiang	CN		47.34	123.20	106384
Longjing	CN		42.77	129.42	117185
Longling County	CN		24.59	98.69	270000
Longmeadow	US	Massachusetts	42.05	-72.58	15784
Longmont	US	Colorado	40.17	-105.10	92088
Longnan	CN		33.40	104.92	85826
Longonjo	AO		-12.91	15.25	92103
Longquan	CN		24.67	102.16	91534
Longshan	CN		42.89	125.14	465249
Longshan	CN		24.60	98.70	65192
Longshi	CN		30.21	106.46	56142
Longshui	CN		29.57	105.76	121609
Longsight	GB		53.46	-2.20	16007
Longtan	CN		28.76	108.96	57769
Longton	GB		52.98	-2.13	27214
Longueuil	CA		45.52	-73.47	229330
Longview	US	Texas	32.50	-94.74	82287
Longview	US	Washington	46.14	-122.94	36848
Longyan	CN		25.07	117.02	1025087
Longyearbyen	SJ		78.22	15.65	2368
Loni	IN		28.75	77.29	516082
Lop Buri	TH		14.80	100.65	57761
Lorain	US	Ohio	41.45	-82.18	63647
Lorca	ES		37.67	-1.70	93079
Lorena	BR		-22.73	-45.12	84855
Lorient	FR		47.75	-3.37	58112
Lorton	US	Virginia	38.70	-77.23	18610
Los Altos	US	California	37.39	-122.11	30671
Los Andes	CL		-32.83	-70.60	63009
Los Angeles	US	California	34.05	-118.24	3820914
Los Banos	US	California	37.06	-120.85	37457
Los Baños	PH		14.17	121.24	117030
Los Dos Caminos	VE		10.49	-66.83	58168
Los Gatos	US	California	37.23	-121.97	30705
Los Lunas	US	New Mexico	34.81	-106.73	15336
Los Mochis	MX		25.79	-109.00	256613
Los Patios	CO		7.84	-72.50	58661
Los Polvorines	AR		-34.50	-58.71	53354
Los Puertos de Altagracia	VE		10.71	-71.52	101527
Los Rastrojos	VE		10.03	-69.24	100497
Los Reyes Acaquilpan	MX		19.36	-98.98	85359
Los Teques	VE		10.35	-67.04	252242
Los Ángeles	CL		-37.47	-72.35	125430
Loudi	CN		27.73	111.99	497171
Louga	SN		15.62	-16.22	113365
Loughborough	GB		52.77	-1.20	64884
Lougheed	CA		49.25	-122.89	15300
Loughton	GB		52.43	-2.57	33346
Louis Trichardt	ZA		-23.04	29.90	86854
Louisville	US	Kentucky	38.25	-85.76	624444
Louisville	US	Colorado	39.98	-105.13	20396
Loum	CM		4.72	9.74	58554
Loures	PT		38.83	-9.17	66231
Loushanguan	CN		28.14	106.82	80344
Louth	GB		53.37	-0.00	17382
Louveira	BR		-23.09	-46.95	51847
Loveland	US	Colorado	40.40	-105.07	75182
Loves Park	US	Illinois	42.32	-89.06	23455
Lowell	US	Massachusetts	42.63	-71.32	110699
Lower Earley	GB		51.43	-0.92	32000
Lower Hutt	NZ		-41.22	174.92	114200
Lower Lonsdale	CA		49.31	-123.07	19718
Lower Moyamensing	US	Pennsylvania	39.92	-75.16	16481
Lower Sackville	CA		44.78	-63.68	51749
Lower West Side	US	Illinois	41.85	-87.67	34410
Lowestoft	GB		52.48	1.75	71327
Lozova	UA		48.89	36.31	54026
Lqoliaa	MA		30.30	-9.47	90890
Luancheng	CN		37.88	114.65	597130
Luanda	AO		-8.84	13.23	2776168
Luang Prabang	LA		19.89	102.15	55027
Luanshya	ZM		-13.14	28.42	193293
Luau	AO		-10.71	22.22	55432
Lubango	AO		-14.92	13.49	600751
Lubao	PH		14.94	120.60	55645
Lubbock	US	Texas	33.58	-101.86	249042
Lubin	PL		51.40	16.20	77532
Lublin	PL		51.25	22.57	336339
Lubu	CN		23.17	112.28	95820
Lubuklinggau	ID		-3.29	102.86	234166
Lubumbashi	CD		-11.66	27.48	2221925
Lucan	IE		53.36	-6.45	15269
Lucapa	AO		-8.42	20.74	110000
Lucas do Rio Verde	BR		-13.07	-55.91	92256
Lucca	IT		43.84	10.50	81748
Lucena	PH		13.93	121.62	228758
Lucheng	CN		31.23	117.28	89119
Luckeesarai	IN		25.18	86.09	99979
Lucknow	IN		26.84	80.92	2472011
Ludhiana	IN		30.91	75.85	1618879
Ludlow	US	Massachusetts	42.16	-72.48	22201
Ludwigsburg	DE		48.90	9.19	87603
Ludwigshafen am Rhein	DE		49.48	8.45	163196
Luena	AO		-11.78	19.92	273675
Lufkin	US	Texas	31.34	-94.73	36333
Lugano	CH		46.01	8.96	63185
Lugazi	UG		0.37	32.94	128400
Lugo	ES		43.01	-7.56	98025
Luhansk	UA		48.57	39.31	397677
Luis Eduardo Magalhães	BR		-12.09	-45.79	107909
Luján	AR		-34.57	-59.11	97363
Luleå	SE		65.58	22.15	77832
Lulou	CN		34.72	116.77	63704
Lumajang	ID		-8.13	113.22	123626
Lumberton	US	North Carolina	34.62	-79.01	21667
Lund	SE		55.71	13.19	87244
Lunglei	IN		22.89	92.74	57011
Luocheng	CN		29.38	104.03	73581
Luodian	CN		31.42	121.33	118323
Luohe	CN		33.57	114.03	1294974
Luohu District	CN		22.55	114.13	1143801
Luohuang	CN		29.35	106.44	71515
Luojiang	CN		31.30	104.50	212186
Luojing	CN		31.48	121.34	54329
Luomen	CN		34.75	105.02	89998
Luorong	CN		24.41	109.61	67593
Luoyang	CN		34.67	112.44	1390581
Luoyang	CN		23.16	114.27	123144
Luoyang	CN		24.96	118.68	66188
Lupon	PH		6.90	126.01	68717
Luputa	CD		-7.16	23.70	54676
Luquembo	AO		-10.74	17.72	69420
Lusail	QA		25.42	51.51	198600
Lusaka	ZM		-15.41	28.29	2212301
Lushar	CN		36.48	101.56	67153
Lushnjë	AL		40.94	19.70	63135
Lushui	CN		25.82	98.86	197000
Lutes Mountain	CA		46.14	-64.91	16311
Lutherville-Timonium	US	Maryland	39.44	-76.61	15814
Luton	GB		51.88	-0.42	225262
Lutsk	UA		50.76	25.35	215986
Lutz	US	Florida	28.15	-82.46	19344
Luxembourg	LU		49.61	6.13	76684
Luxor	EG		25.70	32.64	422407
Luzern	CH		47.05	8.31	81691
Luzhou	CN		28.89	105.43	998900
Luziânia	BR		-16.25	-47.95	209129
Lu’an	CN		31.74	116.52	1644344
Lviv	UA		49.84	24.02	717273
Lynbrook	US	New York	40.65	-73.67	19558
Lynchburg	US	Virginia	37.41	-79.14	79812
Lyndhurst	US	New Jersey	40.81	-74.12	19996
Lynn	US	Massachusetts	42.47	-70.95	92457
Lynn Haven	US	Florida	30.25	-85.65	20156
Lynnwood	US	Washington	47.82	-122.32	36997
Lynwood	US	California	33.93	-118.21	71989
Lyon	FR		45.75	4.85	520774
Lyon 03	FR		45.76	4.85	102725
Lyon 06	FR		45.77	4.85	52862
Lyon 07	FR		45.75	4.84	82573
Lyon 08	FR		45.74	4.87	86154
Lyon 09	FR		45.77	4.80	51983
Lysychansk	UA		48.91	38.42	93340
Lys’va	RU		58.11	57.81	68660
Lytham St Annes	GB		53.74	-3.00	42695
Lytkarino	RU		55.58	37.91	50619
Lyubertsy	RU		55.68	37.89	154650
Lyublino	RU		55.68	37.76	172000
Lào Cai	VN		22.49	103.97	130671
Lárisa	GR		39.63	22.42	146926
Léo	BF		11.10	-2.11	51743
Léogâne	HT		18.51	-72.63	134190
Lévis	CA		46.80	-71.18	143414
Lübeck	DE		53.87	10.69	212207
Lüdenscheid	DE		51.22	7.63	79386
Lüeyang Chengguanzhen	CN		33.33	106.15	67496
Lüleburgaz	TR		41.40	27.36	90899
Lüliang	CN		37.52	111.14	3346500
Lüneburg	DE		53.25	10.42	71260
Lünen	DE		51.62	7.53	91009
Lüshun	CN		38.80	121.27	82345
Lādnūn	IN		27.65	74.40	65575
Lāharpur	IN		27.71	80.90	55911
Lāhījān	IR		37.20	50.01	101073
Lākshām	BD		23.24	91.12	82290
Lār	IR		27.68	54.34	62045
Lạng Sơn	VN		21.85	106.76	200108
M'Sila	DZ		35.71	4.54	132975
Ma On Shan	HK		22.41	114.24	215200
Ma'an	JO		30.20	35.73	50350
Maastricht	NL		50.85	5.69	122378
Maba	CN		24.68	113.60	113609
Mabai	CN		23.01	104.45	63569
Mabalacat City	PH		15.22	120.57	188050
Mableton	US	Georgia	33.82	-84.58	37115
Mabopane	ZA		-25.51	28.06	110972
Macapá	BR		0.04	-51.07	512902
Macau	MO		22.20	113.55	649335
Macaé	BR		-22.38	-41.78	143029
Macaíba	BR		-5.86	-35.35	82249
Macclesfield	GB		53.26	-2.13	54345
Maceió	BR		-9.67	-35.74	1031597
Macenta	GN		8.54	-9.47	68020
Machakos	KE		-1.52	37.27	63767
Machala	EC		-3.26	-79.96	289141
Macheng	CN		31.18	115.02	126366
Machesney Park	US	Illinois	42.35	-89.04	22927
Machida	JP		35.54	139.45	431079
Machilīpatnam	IN		16.19	81.14	192827
Machiques	VE		10.06	-72.55	132734
Mackay	AU		-21.15	149.17	84333
Maco	PH		7.36	125.86	87680
Macomb	US	Illinois	40.46	-90.67	18547
Macon	US	Georgia	32.84	-83.63	91351
Madanapalle	IN		13.55	78.50	180180
Madaripur	BD		23.17	90.21	84789
Madera	US	California	36.96	-120.06	64208
Madgaon	IN		15.28	73.96	87650
Madhavaram	IN		13.15	80.23	119105
Madhepura	IN		25.92	86.79	54472
Madhubani	IN		26.35	86.07	75736
Madhupur	IN		24.27	86.64	55238
Madhurampur Dehri	IN		24.97	84.20	137231
Madhyamgram	IN		22.69	88.45	161126
Madhyapur Thimi	NP		27.68	85.39	119955
Madido	ZM		-15.35	28.37	80782
Madinah	SA		24.47	39.61	1300000
Madison	US	Wisconsin	43.07	-89.40	280305
Madison	US	Alabama	34.70	-86.75	46962
Madison	US	Mississippi	32.46	-90.12	25799
Madison	US	Connecticut	41.28	-72.60	19100
Madison	US	New Jersey	40.76	-74.42	16126
Madison Heights	US	Michigan	42.49	-83.11	30198
Madisonville	US	Kentucky	37.33	-87.50	19539
Madiun	ID		-7.63	111.52	202544
Madrid	ES		40.42	-3.70	3255944
Madrid	CO		4.73	-74.26	135000
Madrid Centro	ES		40.42	-3.70	149718
Madurai	IN		9.92	78.12	1465625
Maduravoyal	IN		13.07	80.16	86195
Madīnat an Naşr	EG		30.07	31.30	668413
Madīnat as Sādāt	EG		30.37	30.51	71501
Madīnat Ḩamad	BH		26.12	50.51	133550
Maebaru-chūō	JP		33.56	130.20	70339
Maebashi	JP		36.40	139.08	332149
Maesteg	GB		51.61	-3.66	21001
Mafikeng	ZA		-25.87	25.64	77110
Mafinga	TZ		-8.30	35.29	99305
Mafra	BR		-26.11	-49.81	55286
Mafraq	JO		32.34	36.21	57118
Magadan	RU		59.56	150.80	92782
Magalang	PH		15.22	120.66	68988
Magangué	CO		9.24	-74.75	123982
Magdalena Contreras	MX		19.33	-99.21	238431
Magdeburg	DE		52.13	11.63	244329
Magelang	ID		-7.47	110.22	128709
Maghnia	DZ		34.85	-1.73	87373
Maghull	GB		53.52	-2.94	26997
Maghāghah	EG		28.65	30.84	118223
Magna	US	Utah	40.71	-112.10	26505
Magnitogorsk	RU		53.40	59.01	413351
Magog	CA		45.27	-72.15	15550
Magong	TW		23.57	119.59	63745
Magsaysay	PH		6.77	125.18	57936
Magugpo Poblacion	PH		7.45	125.80	233254
Magway	MM		20.15	94.93	96954
Magé	BR		-22.65	-43.04	244092
Maha Sarakham	TH		16.18	103.30	51584
Mahajanga	MG		-15.72	46.32	260556
Maharagama	LK		6.85	79.93	195355
Mahbūbnagar	IN		16.74	77.99	190400
Mahdia	TN		35.50	11.06	51803
Maheshtala	IN		22.51	88.25	448317
Mahesāna	IN		23.60	72.38	190753
Mahilyow	BY		53.91	30.34	352896
Mahobā	IN		25.29	79.88	89170
Mahuva	IN		21.09	71.77	98519
Mahwah	US	New Jersey	41.09	-74.14	24062
Mahābād	IR		36.76	45.72	168393
Mahāsamund	IN		21.11	82.09	54413
Maianga	AO		-8.85	13.24	727681
Maicao	CO		11.38	-72.24	166603
Maidenhead	GB		51.52	-0.72	70374
Maidstone	GB		51.27	0.52	107627
Maiduguri	NG		11.85	13.16	1110000
Maijdi	BD		22.87	91.10	132185
Maillardville	CA		49.24	-122.87	15837
Mailsi	PK		29.80	72.17	125431
Mainpuri	IN		27.23	79.03	94619
Mainz	DE		49.98	8.28	222889
Maipú	CL		-33.51	-70.77	503635
Maiquetía	VE		10.59	-66.96	52564
Mairinque	BR		-23.55	-47.18	50027
Mairiporã	BR		-23.32	-46.59	101937
Maison Blanche	FR		48.83	2.35	64302
Maisons-Alfort	FR		48.81	2.44	53964
Maitland	AU		-32.73	151.56	89597
Maitland	US	Florida	28.63	-81.36	17463
Maizuru	JP		35.45	135.33	92465
Majadahonda	ES		40.47	-3.87	68110
Majalengka	ID		-6.84	108.23	73052
Majene	ID		-3.54	118.97	73883
Majie	CN		25.03	102.64	131696
Majuro	MH		7.09	171.38	25400
Makakilo	US	Hawaii	21.35	-158.09	18248
Makakilo / Kapolei / Honokai Hale	US	Hawaii	21.34	-158.10	46389
Makakilo City	US	Hawaii	21.35	-158.09	15383
Makakilo-Makaīwa Hills-Kunia	US	Hawaii	21.37	-158.07	20967
Makassar	ID		-5.15	119.43	1474393
Makati City	PH		14.55	121.03	510383
Makeni	SL		8.89	-12.04	85116
Makhachkala	RU		42.98	47.50	596356
Makiki / Lower Punchbowl / Tantalus	US	Hawaii	21.32	-157.83	31434
Makiyivka	UA		48.05	37.93	338968
Makkah	SA		21.43	39.83	1578722
Makoko	NG		6.50	3.39	85840
Makrāna	IN		27.04	74.72	94487
Makumbako	TZ		-8.85	34.83	116232
Makurdi	NG		7.73	8.52	390000
Malabo	GQ		3.76	8.78	155963
Malabon	PH		14.67	120.94	365525
Malacatán	GT		14.91	-92.06	92816
Malacca	MY		2.20	102.24	579000
Maladziečna	BY		54.32	26.85	87339
Malahide	IE		53.45	-6.15	16550
Malakal	SS		9.53	31.66	160765
Malambo	CO		10.86	-74.77	129148
Malang	ID		-7.98	112.63	889359
Malanje	AO		-9.54	16.34	455000
Malanville	BJ		11.87	3.38	64639
Malapatan	PH		5.97	125.29	82577
Malappuram	IN		11.04	76.08	101386
Malatia-Sebastia	AM		40.17	44.45	150500
Malatya	TR		38.35	38.32	750491
Malaybalay	PH		8.16	125.13	61524
Malda	IN		25.00	88.15	170039
Malden	US	Massachusetts	42.43	-71.07	61068
Maldon	GB		51.73	0.67	23380
Maldonado	UY		-34.90	-54.95	102000
Male	MV		4.18	73.51	103693
Malegaon	IN		20.55	74.53	481228
Malindi	KE		-3.22	40.12	119859
Malingao	PH		7.16	124.47	1121974
Malingshan	CN		34.20	118.36	52711
Malir Cantonment	PK		24.94	67.21	300000
Malita	PH		6.42	125.61	118438
Malkajgiri	IN		17.45	78.53	150000
Malkāpur	IN		20.89	76.20	67740
Mallawī	EG		27.73	30.84	212628
Malmö	SE		55.61	13.00	362133
Malolos	PH		14.84	120.81	269809
Malout	IN		30.21	74.48	81406
Maltby	GB		53.42	-1.20	17513
Maltepe	TR		40.94	29.16	427040
Malumfashi	NG		11.79	7.62	70709
Maluñgun	PH		6.28	125.28	52248
Malvern	CA		43.81	-79.22	43794
Malvern East	AU		-37.87	145.04	22296
Malārd	IR		35.67	50.98	56745
Malāyer	IR		34.30	48.82	170237
Mamaroneck	US	New York	40.95	-73.73	19375
Mamou	GN		10.38	-12.09	79109
Mamoudzou	YT		-12.78	45.23	54831
Mampong	GH		7.06	-1.40	51745
Man	CI		7.41	-7.55	241969
Manacapuru	BR		-3.30	-60.62	110691
Manado	ID		1.48	124.85	458582
Managua	NI		12.13	-86.25	973087
Manama	BH		26.23	50.59	147074
Manaoag	PH		16.04	120.49	59115
Manas	KG		40.94	72.99	123239
Manassas	US	Virginia	38.75	-77.48	41764
Manassas Park	US	Virginia	38.78	-77.47	15726
Manaung	MM		18.85	93.73	50680
Manaus	BR		-3.10	-60.02	2219580
Manavgat	TR		36.79	31.44	99254
Manbij	SY		36.53	37.95	99497
Mancherial	IN		18.87	79.43	89935
Manchester	GB		53.48	-2.24	568996
Manchester	US	New Hampshire	43.00	-71.45	110229
Manchester	US	Connecticut	41.78	-72.52	30577
Manchester	US	Missouri	38.60	-90.51	18229
Manchester City Centre	GB		53.48	-2.25	17861
Mandalay	MM		21.97	96.08	1208099
Mandaluyong	PH		14.58	121.04	425000
Mandaluyong City	PH		14.58	121.04	465902
Mandamarri	IN		18.97	79.47	66176
Mandan	US	North Dakota	46.83	-100.89	21382
Mandapeta	IN		16.86	81.93	56063
Mandaqui	BR		-23.46	-46.64	103665
Mandaue City	PH		10.32	123.92	331320
Mandela	GH		5.55	-0.34	77371
Mandera	KE		3.94	41.86	114718
Mandi Bahauddin	PK		32.59	73.49	129733
Mandi Dabwāli	IN		29.97	74.70	52873
Mandideep	IN		23.08	77.53	59654
Mandimba	MZ		-14.35	35.65	118922
Mandlā	IN		22.60	80.37	55133
Mandoli	IN		28.70	77.31	120417
Mandsaur	IN		24.07	75.07	141667
Mandurah	AU		-32.53	115.72	107643
Mandya	IN		12.52	76.90	137358
Manfalūţ	EG		27.31	30.97	117925
Manfredonia	IT		41.63	15.92	56932
Mangai	CD		-4.02	19.53	63713
Mangalagiri	IN		16.43	80.57	107197
Mangaldan	PH		16.07	120.40	88818
Mangaluru	IN		12.92	74.86	499487
Mangere	NZ		-36.97	174.80	23310
Mangere East	NZ		-36.97	174.82	28540
Mangina	CD		0.60	29.31	55439
Mango	IN		22.83	86.22	223805
Mangochi	MW		-14.48	35.26	60338
Mangotsfield	GB		51.49	-2.50	36427
Manhattan	US	New York	40.78	-73.97	1487536
Manhattan	US	Kansas	39.18	-96.57	56308
Manhattan Beach	US	California	33.88	-118.41	35818
Manhattan Valley	US	New York	40.79	-73.97	38500
Manhiça	MZ		-25.40	32.81	65240
Manhuaçu	BR		-20.26	-42.03	91886
Manicoré	BR		-5.81	-61.30	57758
Manila	PH		14.60	120.98	1600000
Manisa	TR		38.61	27.43	243971
Manitowoc	US	Wisconsin	44.09	-87.66	33010
Manizales	CO		5.07	-75.51	434403
Manjeri	IN		11.12	76.12	97102
Manjhand	PK		25.91	68.24	140766
Mankato	US	Minnesota	44.16	-94.01	41044
Manly	AU		-33.80	151.29	16170
Manmād	IN		20.25	74.44	80058
Mannargudi	IN		10.67	79.45	66999
Mannheim	DE		49.49	8.47	307960
Mannārakkāt	IN		10.99	76.46	50921
Manoa	US	Hawaii	21.32	-157.80	23343
Manokwari	ID		-0.86	134.06	132300
Manolo Fortich	PH		8.37	124.86	118075
Manono	CD		-7.30	27.40	82465
Manor Park	GB		51.55	0.05	15318
Manp’o	KP		41.15	126.29	116760
Manresa	ES		41.73	1.82	76250
Mansa	ZM		-11.20	28.89	170965
Mansehra	PK		34.33	73.20	66486
Mansfield	GB		53.13	-1.20	171958
Mansfield	US	Texas	32.56	-97.14	64274
Mansfield	US	Ohio	40.76	-82.52	46830
Mansfield	US	Massachusetts	42.03	-71.22	23380
Mansfield City	US	Connecticut	41.77	-72.23	26439
Mansfield Woodhouse	GB		53.16	-1.19	18330
Mansilingan	PH		10.63	122.98	454150
Mansoûra	DZ		34.86	-1.34	52285
Manta	EC		-0.95	-80.73	264281
Mantampay	PH		8.17	124.22	265032
Manteca	US	California	37.80	-121.22	75448
Mantilla	CU		23.07	-82.34	206918
Manukau City	NZ		-36.99	174.88	362000
Manurewa	NZ		-37.02	174.88	40820
Manzanillo	MX		19.12	-104.34	159853
Manzanillo	CU		20.34	-77.12	128188
Manzhouli	CN		49.60	117.43	54808
Manzini	SZ		-26.50	31.38	110537
Manéah	GN		9.73	-13.42	194297
Man’gyŏngdae-ri	KP		38.99	125.66	321690
Mao	TD		14.12	15.31	50681
Maocun	CN		34.38	117.25	57649
Maoming	CN		21.67	110.91	1307802
Maozhou	CN		22.76	113.81	74910
Maple Grove	US	Minnesota	45.07	-93.46	68385
Maple Heights	US	Ohio	41.42	-81.57	22631
Maple Ridge	CA		49.22	-122.60	82256
Maple Shade	US	New Jersey	39.95	-74.99	19077
Maple Valley	US	Washington	47.39	-122.05	25686
Maplewood	US	Minnesota	44.95	-93.00	40567
Maplewood	US	New Jersey	40.73	-74.27	25008
Maputo	MZ		-25.97	32.58	1254837
Maputsoe	LS		-28.89	27.90	61916
Maqin County	CN		34.47	100.24	59900
Mar del Plata	AR		-38.00	-57.56	593337
Mar del Tuyú	AR		-36.57	-56.69	83016
Marabá	BR		-5.38	-49.13	145860
Maracaibo	VE		10.64	-71.61	1752602
Maracanaú	BR		-3.88	-38.63	234509
Maracay	VE		10.25	-67.59	464700
Maradi	NE		13.50	7.10	361702
Maraimalainagar	IN		12.80	80.03	81872
Maramag	PH		7.76	125.01	109864
Maran	MY		3.59	102.77	111056
Marana	US	Arizona	32.44	-111.23	41315
Marand	IR		38.43	45.77	124191
Maranguape	BR		-3.89	-38.69	105093
Marawi City	PH		8.00	124.28	259993
Marbella	ES		36.52	-4.89	156295
Marblehead	US	Massachusetts	42.50	-70.86	19808
Marburg an der Lahn	DE		50.81	8.77	78895
March	GB		52.55	0.09	21051
Marco Island	US	Florida	25.94	-81.72	17690
Marcory	CI		5.31	-3.99	214061
Mardan	PK		34.20	72.05	300424
Mardin	TR		37.31	40.74	129864
Marechal Cândido Rondon	BR		-24.56	-54.06	55836
Marechal Deodoro	BR		-9.71	-35.90	62341
Margahayukencana	ID		-6.97	107.57	83119
Margareten	AT		48.19	16.35	54412
Margate	GB		51.38	1.39	63322
Margate	US	Florida	26.24	-80.21	57234
Marg‘ilon	UZ		40.47	71.72	253500
Mariana	BR		-20.38	-43.42	61387
Marianao	CU		23.07	-82.43	134057
Mariano	PH		8.83	125.12	70516
Mariano Roque Alonso	PY		-25.21	-57.53	72008
Mariara	VE		10.30	-67.72	116142
Maribor	SI		46.56	15.65	96209
Maricopa	US	Arizona	33.06	-112.05	48602
Maricá	BR		-22.92	-42.82	211986
Mariehamn	AX		60.10	19.93	10682
Mariendorf	DE		52.44	13.38	52734
Marienthal	DE		53.57	10.08	287101
Marietta	US	Georgia	33.95	-84.55	59067
Marigot	MF		18.07	-63.08	5700
Marikina City	PH		14.65	121.11	471323
Marilao	PH		14.76	120.95	83276
Marina	US	California	36.68	-121.80	21229
Mariners Harbor	US	New York	40.64	-74.16	19905
Maringá	BR		-23.43	-51.94	409657
Marinilla	CO		6.17	-75.34	57403
Marion	US	Iowa	42.03	-91.60	37330
Marion	US	Ohio	40.59	-83.13	36363
Marion	US	Indiana	40.56	-85.66	29081
Marion	US	Illinois	37.73	-88.93	17803
Marion Oaks	US	Florida	29.01	-82.18	19034
Marituba	BR		-1.36	-48.34	111785
Mariupol	UA		47.10	37.54	230000
Mariveles	PH		14.43	120.49	156200
Marj Al Hamam	JO		31.90	35.85	82788
Marka	SO		1.72	44.77	230100
Markala	ML		13.68	-6.07	53738
Market Harborough	GB		52.48	-0.92	24779
Markham	CA		43.87	-79.27	338503
Marl	DE		51.66	7.09	91398
Marlboro	US	New Jersey	40.32	-74.25	40191
Marlborough	US	Massachusetts	42.35	-71.55	39818
Marlow	GB		51.57	-0.77	18261
Marne La Vallée	FR		48.84	2.64	318325
Marondera	ZW		-18.19	31.55	66204
Maroochydore	AU		-26.66	153.10	18342
Maroua	CM		10.59	14.32	314122
Maroubra	AU		-33.95	151.23	30224
Maroúsi	GR		38.05	23.80	72333
Marpole	CA		49.21	-123.13	27843
Marquette	US	Michigan	46.54	-87.40	21297
Marrakesh	MA		31.63	-8.00	995871
Marrero	US	Louisiana	29.90	-90.10	33141
Marrickville	AU		-33.91	151.16	26140
Marsala	IT		37.80	12.44	77915
Marseille	FR		43.30	5.38	877215
Marseille 08	FR		43.27	5.38	78837
Marseille 09	FR		43.25	5.41	76868
Marseille 10	FR		43.28	5.42	51299
Marseille 11	FR		43.29	5.44	56792
Marseille 12	FR		43.30	5.44	58734
Marseille 13	FR		43.32	5.41	89316
Marseille 14	FR		43.34	5.38	61920
Marseille 15	FR		43.37	5.35	77770
Marshall	US	Texas	32.54	-94.37	23820
Marshalltown	US	Iowa	42.05	-92.91	27620
Marshfield	US	Wisconsin	44.67	-90.17	18620
Marsá Maţrūḩ	EG		31.35	27.24	176498
Martapura	ID		-3.41	114.86	131449
Martha Lake	US	Washington	47.85	-122.24	15473
Martil	MA		35.62	-5.28	70274
Martin	SK		49.07	18.92	51139
Martinez	US	California	38.02	-122.13	38137
Martinez	US	Georgia	33.52	-82.08	35795
Martinsburg	US	West Virginia	39.46	-77.96	17700
Martínez de la Torre	MX		20.07	-97.06	60074
Marudi	MY		4.18	114.32	90100
Marugame	JP		34.28	133.78	109513
Marvdasht	IR		29.87	52.80	148858
Mary	TM		37.59	61.83	167027
Maryborough	AU		-25.54	152.70	27489
Maryland City	US	Maryland	39.09	-76.82	16093
Maryland Heights	US	Missouri	38.71	-90.43	27389
Marysville	US	Washington	48.05	-122.18	66773
Marysville	US	Ohio	40.24	-83.37	22817
Maryvale	US	Arizona	33.50	-112.18	208189
Maryville	US	Tennessee	35.76	-83.97	28464
Marzahn	DE		52.55	13.57	111508
Marília	BR		-22.21	-49.95	240590
Marāgheh	IR		37.39	46.24	262604
Marāgheh	IR		35.83	59.63	262604
Marīvān	IR		35.52	46.18	136654
Mar’ino	RU		55.65	37.72	243000
Masai	MY		1.49	103.88	141730
Masaka	UG		-0.33	31.73	116600
Masan	KR		35.13	126.83	434371
Masasi	TZ		-10.72	38.80	89700
Masaurhi Buzurg	IN		25.35	85.03	59803
Masaya	NI		11.97	-86.10	130113
Mascara	DZ		35.40	0.14	108629
Mascot	AU		-33.93	151.19	15985
Mascouche	CA		45.75	-73.60	34626
Maseru	LS		-29.32	27.48	359753
Mashhad	IR		36.30	59.61	2307177
Mashtūl as Sūq	EG		30.36	31.38	75837
Masina	CD		-4.38	15.39	485167
Masindi	UG		1.67	31.71	110500
Masinloc	PH		15.54	119.95	56579
Masjed Soleymān	IR		31.94	49.30	100497
Mason	US	Ohio	39.36	-84.31	32662
Mason City	US	Iowa	43.15	-93.20	27366
Maspeth	US	New York	40.72	-73.91	48325
Massa	IT		44.04	10.14	64783
Massapequa	US	New York	40.68	-73.47	21685
Massapequa Park	US	New York	40.68	-73.46	17232
Massey	NZ		-36.84	174.61	22210
Massey East	NZ		-36.83	174.62	22210
Massillon	US	Ohio	40.80	-81.52	32252
Masterton	NZ		-40.96	175.66	28900
Mastic	US	New York	40.80	-72.84	15481
Masumbwe	TZ		-3.63	32.18	50000
Masvingo	ZW		-20.06	30.83	90286
Matadi	CD		-5.84	13.46	425662
Matagalpa	NI		12.93	-85.92	109089
Matala	AO		-14.73	15.03	78000
Matamoros	MX		25.53	-103.23	52233
Matanzas	CU		23.04	-81.58	146733
Matara	LK		5.95	80.54	76254
Mataram	ID		-8.58	116.12	441147
Mataró	ES		41.54	2.44	126988
Mateare	NI		12.24	-86.43	61234
Matehuala	MX		23.65	-100.64	77328
Matera	IT		40.67	16.60	60403
Mathura	IN		27.50	77.67	330511
Mati	PH		6.96	126.22	105908
Matilda Estate	SG		1.40	103.90	52200
Matli	PK		25.04	68.66	50398
Matola	MZ		-25.96	32.46	1198988
Matsubara	JP		34.57	135.55	130855
Matsudo	JP		35.78	139.90	498575
Matsue	JP		35.48	133.05	203616
Matsumoto	JP		36.23	137.97	241145
Matsusaka	JP		34.58	136.54	159145
Matsutō	JP		36.52	136.57	110408
Matsuyama	JP		33.84	132.77	511192
Mattapan	US	Massachusetts	42.27	-71.09	36299
Matteson	US	Illinois	41.50	-87.71	19195
Matthews	US	North Carolina	35.12	-80.72	30678
Mattoon	US	Illinois	39.48	-88.37	18113
Matuga	KE		-4.17	39.57	194252
Maturín	VE		9.75	-63.18	647459
Matão	BR		-21.60	-48.37	79033
Mau	IN		25.94	83.56	246050
Mauban	PH		14.19	121.73	70135
Maulavi Bāzār	BD		24.49	91.77	57441
Mauldin	US	South Carolina	34.78	-82.31	25135
Maumelle	US	Arkansas	34.87	-92.40	17931
Maumere	ID		-8.62	122.21	87720
Maun	BW		-19.98	23.42	85350
Mauá	BR		-23.67	-46.46	418261
Maués	BR		-3.38	-57.72	65714
Mawlai-Mawïong	IN		25.62	91.88	55012
Mawlamyine	MM		16.49	97.63	438861
Mawāna	IN		29.10	77.92	76973
Maxixe	MZ		-23.86	35.35	126408
Mayagüez	PR		18.20	-67.14	73077
Mayfield Heights	US	Ohio	41.52	-81.46	18840
Mayiladuthurai	IN		11.10	79.66	86660
Maykop	RU		44.61	40.10	141970
Maymana	AF		35.92	64.78	75900
Maynooth	IE		53.38	-6.59	17259
Maywood	US	California	33.99	-118.19	27888
Maywood	US	Illinois	41.88	-87.84	24012
Maywood	CA		49.22	-123.01	19650
Mazabuka	ZM		-15.86	27.75	104412
Mazara del Vallo	IT		37.66	12.59	51534
Mazatenango	GT		14.53	-91.50	77431
Mazatlán	MX		23.22	-106.42	381583
Mazyr	BY		52.04	29.22	104517
Mazār-e Sharīf	AF		36.71	67.11	523300
Maţāy	EG		28.42	30.78	82328
Ma’anshan	CN		31.69	118.51	741531
Mbabane	SZ		-26.32	31.13	76218
Mbaké	SN		14.79	-15.91	101451
Mbale	UG		1.08	34.18	111300
Mbale	KE		0.08	34.72	60000
Mbalmayo	CM		3.52	11.50	82384
Mbandaka	CD		0.05	18.26	455011
Mbanza Kongo	AO		-6.27	14.24	148000
Mbanza-Ngungu	CD		-5.26	14.86	142773
Mbarara	UG		-0.60	30.65	221300
Mbera	MR		15.86	-5.79	58985
Mbeya	TZ		-8.90	33.45	541603
Mbinga	TZ		-10.93	35.02	60868
Mbombela	ZA		-25.48	30.97	110159
Mbouda	CM		5.63	10.25	71867
Mbour	SN		14.42	-16.96	284189
Mbuji-Mayi	CD		-6.14	23.59	2101332
McAlester	US	Oklahoma	34.93	-95.77	18310
McAllen	US	Texas	26.20	-98.23	140269
McCully - Moiliili	US	Hawaii	21.29	-157.83	28249
McDonough	US	Georgia	33.45	-84.15	23417
McHenry	US	Illinois	42.33	-88.27	26657
McKeesport	US	Pennsylvania	40.35	-79.86	19453
McKenzie Towne	CA		50.91	-113.97	17505
McKinley Park	US	Illinois	41.83	-87.67	15612
McKinleyville	US	California	40.95	-124.10	15177
McKinney	US	Texas	33.20	-96.62	162898
McLean	US	Virginia	38.93	-77.18	48115
McMinnville	US	Oregon	45.21	-123.20	33892
Mdantsane	ZA		-32.93	27.78	205504
Mdiq	MA		35.68	-5.33	61398
Mead Valley	US	California	33.83	-117.30	18510
Meadow Woods	US	Florida	28.39	-81.37	25558
Meadowbrook	US	Virginia	37.45	-77.47	18312
Meads	US	Kentucky	38.41	-82.71	288649
Meaux	FR		48.96	2.88	53811
Mechanicsville	US	Virginia	37.61	-77.37	36348
Mechelen	BE		51.03	4.48	77530
Mecheria	DZ		33.54	-0.28	65043
Medan	ID		3.58	98.67	2486283
Medellín	CO		6.25	-75.57	1999979
Medenine	TN		33.35	10.51	71406
Medford	US	Oregon	42.33	-122.88	79805
Medford	US	Massachusetts	42.42	-71.11	57403
Medford	US	New York	40.82	-73.00	24142
Medianeira	BR		-25.30	-54.09	54369
Mediaş	RO		46.17	24.35	53040
Medicine Hat	CA		50.04	-110.68	63138
Medina	US	Ohio	41.14	-81.86	26339
Medina Estates	GH		5.67	-0.16	101207
Medininagar	IN		24.04	84.07	78396
Medinīpur	IN		22.42	87.32	153349
Meerbusch	DE		51.25	6.69	54826
Meerut	IN		28.98	77.71	1223184
Meguro	JP		35.63	139.70	288088
Mehestan	IR		35.99	50.75	85200
Mehlville	US	Missouri	38.51	-90.32	28380
Meidling	AT		48.17	16.33	97624
Meihekou	CN		42.53	125.68	99419
Meikle Earnock	GB		55.75	-4.03	54480
Meiktila	MM		20.88	95.86	177442
Meishan	CN		30.04	103.84	1107742
Meizhou	CN		24.29	116.12	992351
Mejicanos	SV		13.72	-89.19	160317
Mek'ele	ET		13.50	39.48	457900
Meknes	MA		33.89	-5.55	568295
Mek’ī	ET		8.15	38.82	75200
Melati	ID		-7.73	110.37	67090
Melbourne	AU		-37.81	144.96	5435590
Melbourne	US	Florida	28.08	-80.61	84678
Melbourne City Centre	AU		-37.82	144.97	60057
Meleuz	RU		52.96	55.93	65362
Melilla	ES		35.29	-2.94	85985
Melipilla	CL		-33.69	-71.22	63100
Melitopol	UA		46.85	35.38	148851
Melksham	GB		51.37	-2.14	19357
Mellit	SD		14.13	25.55	50165
Melo	UY		-32.37	-54.16	56013
Melong	CM		5.12	9.96	76716
Melrose	US	Massachusetts	42.46	-71.07	27997
Melrose	US	New York	40.82	-73.91	22470
Melrose Park	US	Illinois	41.90	-87.86	25379
Melton Mowbray	GB		52.77	-0.89	27737
Melville	US	New York	40.79	-73.42	18985
Memphis	US	Tennessee	35.15	-90.05	633104
Menasha	US	Wisconsin	44.20	-88.45	17572
Mendaha	ID		-1.02	103.59	56268
Menden	DE		51.44	7.78	52452
Mendip	GB		51.24	-2.63	110000
Mendoza	AR		-32.89	-68.85	114893
Mene Grande	VE		9.85	-70.93	60580
Menemen	TR		38.61	27.07	53489
Mengcheng Chengguanzhen	CN		33.27	116.57	69916
Menghuan	CN		24.44	98.58	99970
Menglang	CN		22.56	99.91	86877
Mengmao	CN		24.00	97.86	112578
Mengyin	CN		35.71	117.93	65889
Mengzi	CN		23.37	103.38	595100
Menifee	US	California	33.73	-117.15	87174
Menlo Park	US	California	37.45	-122.18	33449
Menomonee Falls	US	Wisconsin	43.18	-88.12	36119
Menomonie	US	Wisconsin	44.88	-91.92	16305
Menongue	AO		-14.66	17.69	251178
Mentor	US	Ohio	41.67	-81.34	46901
Mentougou	CN		39.94	116.09	197772
Menzel Bourguiba	TN		37.15	9.79	58800
Mequon	US	Wisconsin	43.22	-88.03	23132
Merauke	ID		-8.50	140.41	116864
Merced	US	California	37.30	-120.48	82436
Mercedes	AR		-34.65	-59.43	63284
Mercedes	PH		14.11	123.01	53702
Mercedes	US	Texas	26.15	-97.91	16657
Mercer Island	US	Washington	47.57	-122.22	25042
Mercerville-Hamilton Square	US	New Jersey	40.23	-74.67	26419
Mercier–Hochelaga-Maisonneuve	CA		45.57	-73.55	142753
Merelani	TZ		-3.56	36.98	50000
Meriden	US	Connecticut	41.54	-72.81	59988
Meridian	US	Idaho	43.61	-116.39	90739
Meridian	US	Mississippi	32.36	-88.70	39661
Merkezefendi	TR		37.81	29.04	280341
Merlo	AR		-34.67	-58.73	268961
Mernda	AU		-37.60	145.10	23369
Merrick	US	New York	40.66	-73.55	22097
Merrifield	US	Virginia	38.87	-77.23	15212
Merrillville	US	Indiana	41.48	-87.33	35224
Merrimack	US	New Hampshire	42.87	-71.49	26726
Merritt Island	US	Florida	28.36	-80.69	34743
Merrylands	AU		-33.83	150.98	29508
Mersin	TR		36.81	34.64	537842
Merter Keresteciler	TR		41.01	28.89	50000
Merthyr Tydfil	GB		51.75	-3.38	43820
Mertoyudan	ID		-7.52	110.23	69871
Meru	KE		0.05	37.66	80191
Merzifon	TR		40.87	35.46	50658
Mesa	US	Arizona	33.42	-111.82	471825
Meshgīn Shahr	IR		38.40	47.68	74109
Meshkīn Dasht	IR		35.75	50.94	62005
Mesquite	US	Texas	32.77	-96.60	144788
Mesquite	US	Nevada	36.81	-114.07	17496
Messaad	DZ		34.15	3.50	97091
Messina	IT		38.19	15.55	219948
Mestre	IT		45.49	12.25	147662
Metairie	US	Louisiana	29.98	-90.15	138481
Metairie Terrace	US	Louisiana	29.98	-90.16	142489
Methuen	US	Massachusetts	42.73	-71.19	52044
Metpalle	IN		18.85	78.63	50902
Metro	ID		-5.11	105.31	182293
Metrogorodok	RU		55.81	37.79	50000
Metrotown	CA		49.23	-123.00	52355
Mettupalayam	IN		11.30	76.93	69213
Mettur	IN		11.79	77.80	56743
Metu	ET		8.30	35.58	59700
Metz	FR		49.12	6.17	123914
Meulaboh	ID		4.14	96.13	64646
Mexborough	GB		53.49	-1.29	15079
Mexicali	MX		32.63	-115.45	1032686
Mexico City	MX		19.43	-99.13	12294193
Meybod	IR		32.25	54.02	51874
Meycauayan	PH		14.74	120.96	228023
Mezhdurechensk	RU		53.69	88.06	101026
Meïganga	CM		6.52	14.30	59426
Mhow	IN		22.56	75.77	81702
Miabi	CD		-6.22	23.39	79929
Miami	US	Florida	25.77	-80.19	487014
Miami Beach	US	Florida	25.79	-80.13	92312
Miami Gardens	US	Florida	25.94	-80.25	113187
Miami Lakes	US	Florida	25.91	-80.31	30972
Miamisburg	US	Ohio	39.64	-84.29	20034
Mian Channun	PK		30.44	72.36	140112
Mianwali	PK		32.58	71.53	129500
Mianyang	CN		31.47	104.68	1550000
Mianyang	CN		33.16	106.69	84606
Mianzhu, Deyang, Sichuan	CN		31.34	104.22	510000
Miaohang	CN		31.32	121.44	89615
Miaojie	CN		25.31	100.28	62540
Miaoli	TW		24.56	120.82	86327
Miass	RU		55.05	60.11	167500
Micheng	CN		25.34	100.49	89144
Michigan City	US	Indiana	41.71	-86.90	31459
Michurinsk	RU		52.91	40.48	93499
Mid-City	US	California	34.04	-118.36	83000
Middelburg	ZA		-25.78	29.46	196263
Middle River	US	Maryland	39.33	-76.44	25191
Middle Village	US	New York	40.72	-73.88	29491
Middleborough	US	Massachusetts	41.89	-70.91	23116
Middleburg Heights	US	Ohio	41.36	-81.81	15696
Middlesbrough	GB		54.58	-1.23	142707
Middleton	GB		53.55	-2.20	45589
Middleton	US	Wisconsin	43.10	-89.50	18979
Middletown	US	New Jersey	40.39	-74.12	65490
Middletown	US	Ohio	39.52	-84.40	48760
Middletown	US	Connecticut	41.56	-72.65	46756
Middletown	US	New York	41.45	-74.42	27812
Middletown	US	Delaware	39.45	-75.72	20372
Middletown	US	Rhode Island	41.55	-71.29	17303
Midelt	MA		32.69	-4.75	60390
Midland	US	Texas	32.00	-102.08	132524
Midland	US	Michigan	43.62	-84.25	42200
Midland	CA		44.75	-79.88	24353
Midlothian	US	Texas	32.48	-96.99	22318
Midlothian	US	Virginia	37.51	-77.65	18320
Midori	JP		36.44	139.28	50266
Midrand	ZA		-25.98	28.12	87387
Midsayap	PH		7.19	124.53	117365
Midvale	US	Utah	40.61	-111.90	32613
Midway	US	Florida	30.41	-87.01	16115
Midwest City	US	Oklahoma	35.45	-97.40	57249
Midyat	TR		37.42	41.34	76268
Mielec	PL		50.29	21.42	59509
Migori	KE		-1.06	34.47	71668
Miguel Hidalgo	MX		19.43	-99.20	372889
Mihara	JP		34.40	133.08	90573
Mijas	ES		36.60	-4.64	80630
Mikhaylovka	RU		50.06	43.23	58898
Mikhaylovsk	RU		45.13	42.03	59198
Miki	JP		34.80	134.98	75450
Mikkeli	FI		61.69	27.27	51661
Mila	DZ		36.45	6.26	63251
Milagro	EC		-2.13	-79.59	133508
Milan	IT		45.46	9.19	1371498
Mildura	AU		-34.19	142.16	34565
Mile End	CA		45.52	-73.60	23977
Milford	US	Connecticut	41.22	-73.06	52759
Milford	US	Massachusetts	42.14	-71.52	25055
Milford Mill	US	Maryland	39.35	-76.77	29042
Mililani Mauka	US	Hawaii	21.48	-157.99	21075
Mililani Mauka / Launani Valley	US	Hawaii	21.48	-157.99	18072
Mililani Town	US	Hawaii	21.45	-158.02	27629
Mill Creek	US	Washington	47.86	-122.20	20043
Mill Creek East	US	Washington	47.84	-122.19	15709
Mill Park	AU		-37.67	145.07	28712
Millbrae	US	California	37.60	-122.39	22795
Millbrook	US	Alabama	32.48	-86.36	15314
Millburn	US	New Jersey	40.72	-74.30	20149
Millcreek	US	Utah	40.69	-111.88	62139
Milledgeville	US	Georgia	33.08	-83.23	18931
Milliken	CA		43.82	-79.30	26572
Millville	US	New Jersey	39.40	-75.04	28230
Milpitas	US	California	37.43	-121.91	77604
Milton	CA		43.52	-79.88	132979
Milton	US	Georgia	34.13	-84.30	37547
Milton	US	Massachusetts	42.25	-71.07	27003
Milton Keynes	GB		52.04	-0.76	256385
Milwaukee	US	Wisconsin	43.04	-87.91	563531
Milwaukie	US	Oregon	45.45	-122.64	20830
Mimico	CA		43.62	-79.51	33964
Minami-Alps	JP		35.62	138.46	71618
Minami-Sōma	JP		37.63	140.98	59005
Minamiarupusu	JP		35.61	138.46	69459
Minamirinkan	JP		35.50	139.44	224015
Minamiuonuma	JP		37.08	138.87	55354
Minatitlán	MX		18.00	-94.56	112046
Minato	JP		34.22	135.15	375339
Minato City	JP		35.66	139.75	260486
Minbu	MM		20.18	94.88	57342
Minchinabad	PK		30.16	73.57	67164
Mindelo	CV		16.89	-24.98	69013
Minden	DE		52.29	8.91	82879
Mineiros	BR		-17.57	-52.55	70081
Mineola	US	New York	40.75	-73.64	19139
Mineralnye Vody	RU		44.21	43.14	76280
Mingachevir	AZ		40.76	47.06	106048
Mingala Tangnyunt	MM		16.79	96.17	132494
Mingaladon	MM		16.92	96.10	136000
Mingcun	CN		36.75	119.64	53926
Minggang	CN		32.46	114.05	67945
Mingguang	CN		32.78	117.96	68351
Minglanilla	PH		10.24	123.80	62058
Mingora	PK		34.78	72.36	361112
Mingshui	CN		36.72	117.50	114858
Mingshui	CN		47.18	125.90	59369
Minhang	CN		31.11	121.37	2716600
Minna	NG		9.62	6.55	425000
Minneapolis	US	Minnesota	44.98	-93.26	410939
Minnetonka	US	Minnesota	44.91	-93.50	51669
Minnetonka Mills	US	Minnesota	44.94	-93.44	50117
Minoh	JP		34.83	135.47	136868
Minokamo	JP		35.48	137.02	56972
Minot	US	North Dakota	48.23	-101.30	49450
Minsk	BY		53.90	27.57	1742124
Mint Hill	US	North Carolina	35.18	-80.65	25627
Minusinsk	RU		53.70	91.71	72781
Minya	EG		28.09	30.76	283605
Minyat an Naşr	EG		31.13	31.64	82429
Minyā al Qamḩ	EG		30.52	31.35	99284
Mira Mesa	US	California	32.92	-117.14	70000
Mirabel	CA		45.65	-74.08	34626
Miraflores	PE		-12.11	-77.03	187401
Miragoâne	HT		18.45	-73.09	89202
Miramar	US	Florida	25.99	-80.23	137132
Miramar	MX		22.36	-97.90	118614
Miramichi	CA		47.03	-65.50	17537
Miranda	AU		-34.04	151.10	15111
Mirassol	BR		-20.82	-49.52	63337
Mirdif	AE		25.22	55.41	60288
Mirfield	GB		53.67	-1.70	18800
Miri	MY		4.40	113.99	300543
Mirpur Khas	PK		25.53	69.01	267833
Mirpur Mathelo	PK		28.02	69.55	74651
Mirpur Model Thana	BD		23.81	90.36	546503
Miryalaguda	IN		16.87	79.56	104918
Miryang	KR		35.49	128.75	53103
Mirzāpur	IN		25.14	82.57	220029
Misato, Saitama	JP		35.84	139.88	142145
Mishan	CN		45.55	131.88	87257
Mishawaka	US	Indiana	41.66	-86.16	48261
Mishima	JP		35.12	138.92	107851
Miskolc	HU		48.10	20.78	154521
Misratah	LY		32.38	15.09	355657
Mission	US	Texas	26.22	-98.33	83298
Mission	CA		49.13	-122.30	41519
Mission Bend	US	Texas	29.69	-95.66	36501
Mission District	US	California	37.76	-122.42	47234
Mission Hill	US	Massachusetts	42.33	-71.11	18722
Mission Viejo	US	California	33.60	-117.67	97156
Mississauga	CA		43.58	-79.66	717961
Missoula	US	Montana	46.87	-113.99	71022
Missouri City	US	Texas	29.62	-95.54	74139
Mitcham	GB		51.40	-0.17	63393
Mitcham	AU		-37.82	145.20	16795
Mitchell	US	South Dakota	43.71	-98.03	15669
Mithi	PK		24.74	69.80	52376
Mito	JP		36.35	140.45	270685
Mitoyo	JP		34.21	133.67	65713
Mitrovicë	XK		42.88	20.87	107045
Mitte	DE		52.52	13.40	102338
Mityana	UG		0.42	32.02	105200
Miura	JP		35.14	139.62	51483
Mixco	GT		14.63	-90.61	465773
Miyako	JP		39.65	141.94	51150
Miyakojima	JP		24.79	125.31	54908
Miyakonojō	JP		31.73	131.07	161137
Miyang	CN		24.40	103.44	72485
Miyazaki	JP		31.92	131.42	401339
Miyoshi	JP		35.09	137.09	61952
Miyoshi	JP		34.80	132.85	53616
Mizuho	JP		35.39	136.67	56388
Mizusawa	JP		39.13	141.13	61281
Mlolongo	KE		-1.40	36.94	136351
Mmabatho	ZA		-25.85	25.63	76754
Mnihla	TN		36.85	10.11	58641
Moa	CU		20.66	-74.95	92852
Moabit	DE		52.53	13.34	81021
Moanda	CD		-5.93	12.37	128804
Moanda	GA		-1.57	13.20	71099
Mobara	JP		35.43	140.30	88330
Mobile	US	Alabama	30.69	-88.04	183289
Mobārakeh	IR		32.35	51.50	69449
Moca	DO		19.39	-70.52	61834
Mochudi	BW		-24.42	26.15	50321
Mocoa	CO		1.15	-76.65	56398
Mococa	BR		-21.47	-47.00	67681
Mocuba	MZ		-16.84	36.99	196001
Modakeke	NG		7.38	4.26	119529
Model Town	PK		31.48	74.33	100000
Modena	IT		44.65	10.93	184732
Modesto	US	California	37.64	-121.00	211266
Modica	IT		36.86	14.76	54456
Modiin Ilit	IL		31.93	35.04	76374
Modimolle	ZA		-24.70	28.40	50306
Modi‘in Makkabbim Re‘ut	IL		31.89	35.02	93277
Modāsa	IN		23.46	73.30	67648
Moema	BR		-23.60	-46.66	81899
Moers	DE		51.45	6.63	103487
Moga	IN		30.81	75.17	163397
Mogadishu	SO		2.04	45.34	2587183
Mogi das Cruzes	BR		-23.52	-46.19	325746
Mogi Guaçu	BR		-22.37	-46.95	153658
Mogi Mirim	BR		-22.43	-46.96	78244
Mogoditshane	BW		-24.63	25.87	88004
Mogok	MM		22.92	96.51	89855
Mohali	IN		30.68	76.72	166864
Mohammadia	DZ		35.59	0.07	62410
Mohammadpur	BD		24.90	88.53	527571
Mohammed Bin Zayed City	AE		24.35	54.55	85000
Mohammedia	MA		33.69	-7.38	227799
Mojo	ET		8.59	39.12	61300
Mojokerto	ID		-7.47	112.43	141785
Moju	BR		-1.88	-48.77	84094
Mokameh	IN		25.40	85.92	60678
Mokena	US	Illinois	41.53	-87.89	19923
Moknine	TN		35.63	10.90	62802
Mokolo	CM		10.74	13.80	51999
Mokopane	ZA		-24.19	29.01	101090
Mokotów	PL		52.19	21.03	217683
Mokpo	KR		34.81	126.39	268402
Molenbeek-Saint-Jean	BE		50.85	4.31	97037
Molepolole	BW		-24.41	25.50	74861
Molfetta	IT		41.20	16.60	59557
Molina de Segura	ES		38.05	-1.21	64065
Moline	US	Illinois	41.51	-90.52	42681
Mollet del Vallès	ES		41.54	2.21	52484
Molārband	IN		28.50	77.31	91402
Mombasa	KE		-4.05	39.66	1208333
Mon Repos	TT		10.28	-61.45	56380
Monaco	MC		43.74	7.42	32965
Monapo	MZ		-14.92	40.30	50134
Monastir	TN		35.78	10.83	93306
Moncalieri	IT		45.00	7.68	56134
Moncloa-Aravaca	ES		40.44	-3.73	116531
Monclova	MX		26.91	-101.42	215271
Moncton	CA		46.09	-64.80	86106
Mondlo	ZA		-27.98	30.72	53892
Mong Kok	HK		22.32	114.17	62967
Mongaguá	BR		-24.09	-46.62	57648
Mongo	TD		12.19	18.69	53768
Mongu	ZM		-15.25	23.13	111450
Monkayo	PH		7.82	126.05	96405
Monroe	US	Louisiana	32.51	-92.12	49598
Monroe	US	North Carolina	34.99	-80.55	34623
Monroe	US	Michigan	41.92	-83.40	20092
Monroe	US	Washington	47.86	-121.97	18090
Monroeville	US	Pennsylvania	40.42	-79.79	28176
Monrovia	LR		6.30	-10.80	1542549
Monrovia	US	California	34.15	-118.00	37463
Mons	BE		50.45	3.95	95299
Monsanto	PT		39.46	-8.71	50000
Monsey	US	New York	41.11	-74.07	18412
Mont-Royal	CA		45.52	-73.65	18933
Mont-Saint-Hilaire	CA		45.57	-73.19	15720
Montauban	FR		44.02	1.35	52434
Montclair	US	New Jersey	40.83	-74.21	39701
Montclair	US	California	34.08	-117.69	38690
Montclair	US	Virginia	38.61	-77.34	19570
Monte Alegre	BR		-2.00	-54.08	60012
Monte Chingolo	AR		-34.73	-58.35	85060
Monte Mor	BR		-22.95	-47.32	64662
Montebello	US	California	34.01	-118.11	63921
Montego Bay	JM		18.47	-77.92	82867
Montelíbano	CO		7.98	-75.42	90450
Montemorelos	MX		25.19	-99.83	67428
Montenegro	BR		-29.69	-51.46	65721
Montepuez	MZ		-13.13	39.00	88442
Monterey	US	California	36.60	-121.89	28338
Monterey Park	US	California	34.06	-118.12	61468
Montero	BO		-17.34	-63.25	88616
Monterrey	MX		25.68	-100.32	1135512
Montería	CO		8.75	-75.88	490935
Montes Claros	BR		-16.73	-43.86	414240
Montesilvano	IT		42.51	14.15	53275
Montevideo	UY		-34.90	-56.19	1270737
Montgomery	US	Alabama	32.37	-86.30	195287
Montgomery	US	Illinois	41.73	-88.35	19489
Montgomery Village	US	Maryland	39.18	-77.20	32032
Montpellier	FR		43.61	3.88	248252
Montreuil	FR		48.86	2.44	111240
Montrose	US	Colorado	38.48	-107.88	19062
Montréal	CA		45.51	-73.59	1762949
Montréal-Nord	CA		45.60	-73.63	86857
Montville Center	US	Connecticut	41.48	-72.15	20180
Monywa	MM		22.11	95.14	182011
Monza	IT		45.58	9.27	124398
Monze	ZM		-16.27	27.48	60281
Mooca	BR		-23.56	-46.60	80880
Mooka	JP		36.43	140.02	78720
Moonee Ponds	AU		-37.77	144.92	16224
Moonniyur	IN		11.06	75.90	55535
Moore	US	Oklahoma	35.34	-97.49	60451
Mooresville	US	North Carolina	35.58	-80.81	36009
Moorhead	US	Minnesota	46.87	-96.77	42005
Mooroolbark	AU		-37.78	145.32	23059
Moorpark	US	California	34.29	-118.88	36104
Moose Jaw	CA		50.40	-105.53	33890
Mopti	ML		14.48	-4.18	186187
Moquegua	PE		-17.20	-70.94	69882
Mora	CM		11.05	14.14	61523
Morada Nova	BR		-5.11	-38.37	61443
Moraga	US	California	37.83	-122.13	17256
Moramanga	MG		-18.95	48.23	60456
Moratalaz	ES		40.41	-3.65	104923
Moratuwa	LK		6.77	79.88	168280
Morayfield	AU		-27.11	152.95	21221
Morden	GB		51.40	-0.20	48233
Morecambe	GB		54.07	-2.86	51644
Morelia	MX		19.70	-101.18	743275
Morena	IN		26.50	78.00	200482
Moreno	AR		-34.63	-58.79	148290
Moreno	BR		-8.12	-35.09	55292
Moreno Valley	US	California	33.94	-117.23	204198
Moreton	GB		53.40	-3.12	17670
Morgan Hill	US	California	37.13	-121.65	42948
Morgan Park	US	Illinois	41.69	-87.67	22924
Morganton	US	North Carolina	35.75	-81.68	16692
Morgantown	US	West Virginia	39.63	-79.96	30708
Moriguchi	JP		34.73	135.57	143096
Morioka	JP		39.70	141.15	290700
Moriya	JP		35.93	140.00	68777
Moriyama	JP		35.07	135.98	85485
Morley	GB		53.74	-1.60	57385
Morley	AU		-31.89	115.91	22539
Mormugao	IN		15.39	73.81	102345
Morningside	CA		43.79	-79.21	17455
Morningside Heights	US	New York	40.81	-73.96	55929
Mornington	AU		-38.22	145.04	25759
Moro	PK		26.66	68.00	142685
Morogoro	TZ		-6.82	37.66	471409
Morondava	MG		-20.29	44.32	56671
Moroni	KM		-11.70	43.26	74749
Morphett Vale	AU		-35.13	138.52	24002
Morrinhos	BR		-17.73	-49.10	51351
Morris Heights	US	New York	40.85	-73.92	40982
Morrisania	US	New York	40.83	-73.91	23127
Morristown	US	Tennessee	36.21	-83.29	29478
Morristown	US	New Jersey	40.80	-74.48	18594
Morrisville	US	North Carolina	35.82	-78.83	23820
Morton	US	Illinois	40.61	-89.46	16306
Morton Grove	US	Illinois	42.04	-87.78	23448
Morumbi	BR		-23.60	-46.71	51715
Morvi	IN		22.82	70.84	210451
Morón	AR		-34.65	-58.62	99066
Morón	VE		10.49	-68.20	68084
Morón	CU		22.11	-78.63	66060
Morādābād	IN		28.84	78.78	721139
Moscow	RU		55.75	37.62	10381222
Moscow	US	Idaho	46.73	-117.00	25060
Moses Lake	US	Washington	47.13	-119.28	22082
Moshi	TZ		-3.35	37.33	221733
Mosman	AU		-33.84	151.24	27844
Mosquera	CO		4.71	-74.23	128012
Moss Park	CA		43.65	-79.37	20506
Mossamedes	AO		-15.20	12.15	255000
Mossel Bay	ZA		-34.18	22.15	78940
Mossoró	BR		-5.19	-37.34	264577
Most	CZ		50.50	13.64	63474
Mostaganem	DZ		35.93	0.09	162885
Mostar	BA		43.34	17.81	104518
Mosul	IQ		36.34	43.12	1683000
Motherwell	GB		55.79	-3.99	32840
Mothīhāri	IN		26.65	84.92	126158
Motijheel	BD		23.73	90.42	202308
Motril	ES		36.75	-3.52	60592
Mott Haven	US	New York	40.81	-73.92	51450
Mot’a	ET		11.08	37.87	59000
Moundou	TD		8.57	16.08	196124
Mount Barker	AU		-35.07	138.87	21554
Mount Clemens	US	Michigan	42.60	-82.88	16400
Mount Druitt	AU		-33.77	150.82	16682
Mount Eden	NZ		-36.88	174.76	15650
Mount Eliza	AU		-38.18	145.08	18734
Mount Gambier	AU		-37.83	140.78	25591
Mount Greenwood	US	Illinois	41.70	-87.71	18783
Mount Isa	AU		-20.73	139.50	18317
Mount Juliet	US	Tennessee	36.20	-86.52	31540
Mount Laurel	US	New Jersey	39.93	-74.89	41864
Mount Lebanon	US	Pennsylvania	40.36	-80.05	32730
Mount Martha	AU		-38.27	145.02	19846
Mount Olive-Silverstone-Jamestown	CA		43.75	-79.59	32954
Mount Pearl	CA		47.52	-52.78	22477
Mount Pleasant	US	South Carolina	32.79	-79.86	81317
Mount Pleasant	US	District of Columbia	38.93	-77.04	35842
Mount Pleasant	CA		49.27	-123.10	33000
Mount Pleasant	US	Wisconsin	42.70	-87.86	26272
Mount Pleasant	US	Michigan	43.60	-84.77	26060
Mount Pleasant	US	Texas	33.16	-94.97	16051
Mount Pleasant East	CA		43.70	-79.38	16775
Mount Pleasant West	CA		43.70	-79.39	29658
Mount Prospect	US	Illinois	42.07	-87.94	54747
Mount Vernon	US	New York	40.91	-73.84	68628
Mount Vernon	US	Washington	48.42	-122.33	34053
Mount Vernon	US	Ohio	40.39	-82.49	16742
Mount Vernon	US	Illinois	38.32	-88.90	15087
Mount Vernon Triangle	US	District of Columbia	38.90	-77.02	21897
Mount Waverley	AU		-37.88	145.13	35340
Mountain Brook	US	Alabama	33.50	-86.75	20691
Mountain View	US	California	37.39	-122.08	80435
Mountlake Terrace	US	Washington	47.79	-122.31	20989
Mountsorrel	GB		52.72	-1.15	17297
Mouscron	BE		50.74	3.21	52069
Moyobamba	PE		-6.03	-76.97	50073
Mozambique	MZ		-15.03	40.73	55829
Moḩammad Shahr	IR		35.76	50.92	119418
Moḩammadīyeh	IR		36.22	50.18	90513
Mpanda	TZ		-6.34	31.07	204338
Mpanda	BI		-3.17	29.40	58913
Mpika	ZM		-11.83	31.45	63740
Mpondwe	UG		0.04	29.72	58600
Mpulungu	ZM		-8.76	31.11	55405
Mpumalanga	ZA		-29.81	30.64	140121
Msaken	TN		35.73	10.58	89745
Msalātah	LY		32.58	14.04	73907
Mt Pleasant	CA		49.26	-123.10	32955
Mthatha	ZA		-31.59	28.78	164848
Mtwapa	KE		-3.94	39.75	90677
Mtwara	TZ		-10.27	40.18	140793
Mu-se	MM		24.00	97.90	165022
Muan	KR		34.99	126.48	92009
Muar	MY		2.04	102.57	314776
Mubarakpur	IN		26.09	83.29	53263
Mubende	UG		0.56	31.39	121600
Mubi	NG		10.27	13.27	225705
Mudanjiang	CN		44.55	129.63	665915
Mudhol	IN		16.33	75.28	52199
Mudon	MM		16.26	97.72	89123
Mudu	CN		31.26	120.52	61902
Mueang Nonthaburi	TH		13.86	100.51	254375
Mufulira	ZM		-12.55	28.24	169136
Muhanga	RW		-2.02	29.71	82797
Mui Ne	VN		10.93	108.28	50166
Mujiayingzi	CN		42.12	118.78	60627
Mukachevo	UA		48.44	22.72	85569
Mukalla	YE		14.54	49.12	594951
Mukandpur	IN		28.74	77.18	57135
Mukilteo	US	Washington	47.94	-122.30	21226
Mukim Pulai	MY		1.53	103.67	505661
Mukono	UG		0.35	32.76	191300
Muktsar	IN		30.47	74.52	116747
Mukō	JP		34.97	135.70	56859
Mulbāgal	IN		13.16	78.39	57276
Mulenvos	AO		-8.87	13.33	882014
Mulgrave	AU		-37.93	145.18	19889
Mulhouse	FR		47.75	7.33	111430
Muling	CN		44.92	130.52	66170
Mulongo	CD		-7.83	27.00	89340
Multan	PK		30.20	71.48	2169915
Mulugu	IN		18.19	79.94	297671
Mumbai	IN		19.07	72.88	12691836
Munakata	JP		33.80	130.56	97095
Muncar	ID		-8.43	114.33	64537
Muncie	US	Indiana	40.19	-85.39	70087
Mundelein	US	Illinois	42.26	-88.00	31582
Munger	IN		25.37	86.47	213303
Mungyeong	KR		36.59	128.20	77304
Munich	DE		48.14	11.58	1505005
Munnar	IN		10.09	77.06	68000
Munster	US	Indiana	41.56	-87.51	22984
Muntilan	ID		-7.58	110.29	81555
Muntinlupa	PH		14.39	121.05	552225
Munūf	EG		30.47	30.93	125707
Murakami	JP		38.23	139.48	58300
Muratpaşa	TR		36.89	30.76	450000
Murcia	ES		37.99	-1.13	471982
Murfreesboro	US	Tennessee	35.85	-86.39	165430
Muriaé	BR		-21.13	-42.37	104108
Muricay	PH		7.83	123.48	132094
Muridke	PK		31.80	74.26	254291
Murmansk	RU		68.97	33.10	295374
Murom	RU		55.57	42.02	126931
Muroran	JP		42.32	140.99	96197
Murphy	US	Texas	33.02	-96.61	20610
Murray	US	Utah	40.67	-111.89	49250
Murray	US	Kentucky	36.61	-88.31	18954
Murrieta	US	California	33.55	-117.21	109830
Murrysville	US	Pennsylvania	40.43	-79.70	20134
Murwāra	IN		23.84	80.39	221883
Murādnagar	IN		28.78	77.50	89482
Musaffah	AE		24.36	54.48	243341
Musanze	RW		-1.50	29.63	153368
Musashimurayama	JP		35.74	139.43	70829
Musashino	JP		35.71	139.56	150149
Muscat	OM		23.58	58.41	797000
Muscatine	US	Iowa	41.42	-91.04	23968
Mushie	CD		-3.02	16.92	61336
Mushin	NG		6.53	3.35	199000
Musina	ZA		-22.35	30.04	51132
Muskego	US	Wisconsin	42.91	-88.14	24755
Muskegon	US	Michigan	43.23	-86.25	38401
Muskogee	US	Oklahoma	35.75	-95.37	38456
Musoma	TZ		-1.50	33.80	164172
Musselburgh	GB		55.94	-3.05	23620
Mustafakemalpaşa	TR		40.04	28.41	101412
Mustafābād	IN		28.72	77.27	127167
Mustamäe	EE		59.40	24.68	67968
Mustang	US	Oklahoma	35.38	-97.72	20226
Muswell Hill	GB		51.59	-0.14	27992
Muswellbrook	AU		-32.26	150.89	16000
Mutare	ZW		-18.97	32.67	224802
Mutengene	CM		4.09	9.31	64054
Mutsu	JP		41.29	141.22	56244
Muzaffargarh	PK		30.07	71.19	235541
Muzaffarnagar	IN		29.47	77.70	349706
Muzaffarpur	IN		26.12	85.39	354462
Muzaffarābād	PK		34.37	73.47	725000
Muñoz	PH		15.72	120.90	85061
Muğla	TR		37.22	28.37	92328
Muş	TR		38.73	41.48	82536
Mwala	KE		-1.35	37.45	181896
Mwanza	TZ		-2.52	32.90	1104521
Mweka	CD		-4.85	21.56	81267
Mwene	CD		-9.82	22.87	295683
Mwene-Ditu	CD		-7.01	23.45	189177
My Drarga	MA		30.38	-9.47	55631
Myaungmya	MM		16.60	94.92	58205
Myaydo	MM		19.37	95.22	57395
Myeik	MM		12.44	98.60	173298
Myingyan	MM		21.46	95.39	141713
Myitkyina	MM		25.38	97.40	90894
Mykilska Borshchahivka	UA		50.43	30.37	127400
Mykolayiv	UA		46.98	31.99	470011
Mykytivskyi	UA		48.31	38.00	70474
Mymensingh	BD		24.76	90.41	225126
Myrtle Beach	US	South Carolina	33.69	-78.89	31035
Myrtle Grove	US	Florida	30.42	-87.31	15870
Mysuru	IN		12.30	76.64	920550
Mysłowice	PL		50.21	19.17	72124
Mytishchi	RU		55.91	37.73	160542
Myŏngch’ŏn	KP		41.07	129.43	65797
Myŏnggan-dong	KP		41.14	129.49	99557
Mzuzu	MW		-11.47	34.02	249564
Málaga	ES		36.72	-4.42	592346
Méagui	CI		5.41	-6.56	74365
Médéa	DZ		36.26	2.75	145441
Mérida	MX		20.97	-89.62	1201000
Mérida	VE		8.58	-71.17	300000
Mérida	ES		38.92	-6.34	59857
Mérignac	FR		44.84	-0.65	69791
Móng Cái	VN		21.52	107.97	108553
Móstoles	ES		40.32	-3.86	207095
Mölndal	SE		57.66	12.01	59430
Mönchengladbach	DE		51.19	6.44	261742
Möng Yang	MM		21.85	99.68	117108
Mülheim	DE		51.43	6.88	173050
Münster	DE		51.96	7.63	308258
Mācherla	IN		16.48	79.44	57290
Mādabā	JO		31.72	35.79	82335
Māhdāsht	IR		35.73	50.81	62910
Māler Kotla	IN		30.53	75.88	135424
Māndvi	IN		22.83	69.35	51376
Māngrol	IN		21.12	70.11	69779
Mānikganj	BD		23.86	90.01	71698
Mānsa	IN		29.99	75.40	82956
Mārkāpur	IN		15.74	79.27	71092
Mīnāb	IR		27.13	57.09	97986
Mīt Ghamr	EG		30.72	31.26	153754
Mīthepur	IN		28.50	77.32	69837
Mīzan Teferī	ET		7.00	35.59	62000
Mīāndoāb	IR		36.97	46.11	134425
Mīāneh	IR		37.42	47.72	106291
Mō‘ili‘ili	US	Hawaii	21.29	-157.83	24778
Mūndka	IN		28.68	77.03	54541
Mỹ Hào	VN		20.92	106.08	115608
Mỹ Tho	VN		10.36	106.36	270700
N'dalatando	AO		-9.30	14.91	161584
N'Djamena	TD		12.11	15.04	1359526
Na Di	TH		14.12	101.78	57466
Naas	IE		53.22	-6.67	20713
Nabari	JP		34.62	136.08	77022
Nabarūh	EG		31.10	31.30	59202
Nabatîyé et Tahta	LB		33.38	35.48	120000
Naberezhnyye Chelny	RU		55.74	52.42	509870
Nabeul	TN		36.46	10.74	70437
Nabire	ID		-3.36	135.50	99848
Nablus	PS		32.22	35.25	130326
Nacala	MZ		-14.56	40.69	239808
Nacogdoches	US	Texas	31.60	-94.66	33894
Nada	CN		19.52	109.58	256652
Nadiād	IN		22.69	72.86	225071
Nador	MA		35.17	-2.93	176600
Naesŏ	KR		35.25	128.52	80987
Nag Hammâdi	EG		26.05	32.24	59601
Naga	PH		13.62	123.18	174931
Naga	PH		10.21	123.76	138727
Nagahama	JP		35.38	136.27	113636
Nagakute	JP		35.17	137.06	60162
Nagano	JP		36.65	138.18	372760
Nagaoka	JP		37.45	138.85	266936
Nagaon	IN		26.35	92.67	121628
Nagapattinam	IN		10.76	79.84	102905
Nagar Naluākot	BD		24.16	90.77	273000
Nagareyama	JP		35.86	139.90	200136
Nagari	IN		13.32	79.59	62253
Nagasaki	JP		32.75	129.88	409118
Nagda	IN		23.46	75.42	103501
Nago	JP		26.62	127.99	63554
Nagornyy	RU		55.65	37.62	76000
Nagoya	JP		35.18	136.91	2332176
Nagpur	IN		21.15	79.08	2405665
Nagīna	IN		29.44	78.44	76593
Naha	JP		26.21	127.68	317625
Nahariyya	IL		33.01	35.10	58096
Nahāvand	IR		34.19	48.37	76250
Naic	PH		14.32	120.77	55195
Naihāti	IN		22.89	88.42	253221
Nailsea	GB		51.43	-2.76	20543
Nairobi	KE		-1.28	36.82	4397073
Naivasha	KE		-0.71	36.43	198444
Najaf	IQ		32.03	44.35	482576
Najafgarh	IN		28.61	76.98	1365000
Najafābād	IR		32.63	51.37	235281
Najrān	SA		17.49	44.13	505652
Najībābād	IN		29.61	78.34	84006
Naka	JP		36.05	140.17	53137
Nakano	JP		35.70	139.67	344880
Nakatsu	JP		33.60	131.19	84701
Nakatsugawa	JP		35.48	137.50	78930
Nakhodka	RU		42.84	132.92	146920
Nakhon Pathom	TH		13.82	100.04	117927
Nakhon Ratchasima	TH		14.97	102.10	126391
Nakhon Sawan	TH		15.70	100.14	82305
Nakhon Si Thammarat	TH		8.43	99.97	102152
Nakivale Refugee Camp	UG		-0.74	31.00	68400
Nakonde	ZM		-9.34	32.74	91107
Naksalbāri	IN		26.68	88.22	57283
Nakuru	KE		-0.31	36.07	570674
Nalchik	RU		43.50	43.62	239300
Nalgonda	IN		17.05	79.27	154326
Nallūr	IN		11.10	77.39	70115
Nam Cheong	HK		22.33	114.15	74780
Nam Định	VN		20.43	106.18	448225
Namalombwe	ZM		-15.39	28.19	97758
Namangan	UZ		41.00	71.67	713220
Nametil	MZ		-15.72	39.34	52457
Nampa	US	Idaho	43.54	-116.56	89839
Nampula	MZ		-15.12	39.27	770379
Namp’o	KP		38.74	125.41	455000
Namur	BE		50.47	4.87	110939
Namyang-nodongjagu	KP		42.95	129.86	65956
Namyangju	KR		37.64	127.21	90798
Nanaimo	CA		49.17	-123.94	90504
Nanao	JP		37.05	136.97	50300
Nanbin	CN		30.00	108.11	118597
Nanchang	CN		28.68	115.85	2357839
Nanchong	CN		30.80	106.08	1858875
Nanchuan	CN		29.15	107.10	204775
Nancun	CN		36.53	120.13	124210
Nancy	FR		48.68	6.18	105058
Nandajie	CN		29.34	105.89	88948
Nanded	IN		19.16	77.31	550564
Nanding	CN		36.75	118.06	85495
Nandu	CN		22.85	110.82	61881
Nandurbar	IN		21.37	74.24	111037
Nandyāl	IN		15.48	78.48	211424
Nanfeng	CN		23.73	111.80	86129
Nangen	KR		35.41	127.39	81257
Nangong	CN		37.35	115.39	82386
Nanhu	CN		35.49	119.35	61034
Nani Daman	IN		20.41	72.83	62000
Nanjangūd	IN		12.12	76.68	50598
Nanjian	CN		25.04	100.51	50083
Nanjin	CN		29.98	106.27	143766
Nanjing	CN		32.06	118.78	9314685
Nankana Sahib	PK		31.45	73.71	130041
Nanlong	CN		31.35	106.06	63405
Nanma	CN		36.18	118.15	74406
Nanning	CN		22.82	108.32	3839800
Nanpiao	CN		41.10	120.75	157044
Nanping	CN		26.64	118.17	467875
Nanqiao	CN		30.92	121.45	361185
Nansana	UG		0.36	32.53	532800
Nantai	CN		40.92	122.80	56478
Nanterre	FR		48.89	2.21	86719
Nantes	FR		47.22	-1.55	325070
Nantong	CN		32.03	120.87	2273326
Nantou	CN		22.72	113.29	130370
Nantou	TW		23.92	120.66	105682
Nantwich	GB		53.07	-2.52	17226
Nanuet	US	New York	41.09	-74.01	17882
Nanxi	CN		28.84	104.98	96061
Nanyang	CN		33.01	112.55	1811812
Nanyuki	KE		0.01	37.07	72813
Nanzhang Chengguanzhen	CN		31.78	111.83	83604
Nanzhou	CN		29.36	112.41	54449
Napa	US	California	38.30	-122.29	80434
Naperville	US	Illinois	41.79	-88.15	147100
Napier	NZ		-39.49	176.91	66400
Naples	IT		40.85	14.27	909048
Naples	US	Florida	26.14	-81.80	21512
Naqadeh	IR		36.96	45.39	81598
Nara-shi	JP		34.69	135.80	367353
Narail	BD		23.16	89.50	55112
Narangba	AU		-27.20	152.96	20910
Narasapur	IN		16.43	81.70	59306
Narasaraopet	IN		16.23	80.05	117489
Narashino	JP		35.68	140.04	176197
Narayanganj	BD		23.61	90.50	223622
Narbonne	FR		43.18	3.00	50776
Narela	IN		28.85	77.09	800000
Narita	JP		35.78	140.32	132906
Narmadapuram	IN		22.75	77.73	117988
Narnaul	IN		28.04	76.11	74581
Naro-Fominsk	RU		55.39	36.73	72632
Narok	KE		-1.08	35.87	65430
Narowal	PK		32.10	74.87	130692
Narragansett	US	Rhode Island	41.45	-71.45	15868
Narre Warren	AU		-38.03	145.30	27689
Narre Warren South	AU		-38.04	145.29	30909
Narsimhapur	IN		22.95	79.18	59966
Narsingdi	BD		23.92	90.72	281080
Narutochō-mitsuishi	JP		34.20	134.61	64082
Narva	EE		59.38	28.19	54409
Narwāna	IN		29.60	76.12	62090
Nashik	IN		20.00	73.79	1486053
Nashua	US	New Hampshire	42.77	-71.47	87970
Nashville	US	Tennessee	36.17	-86.78	689447
Nasimshahr	IR		35.57	51.16	200393
Nasinu	FJ		-18.07	178.51	92043
Nasiriyah	IQ		31.06	46.26	558400
Nassau	BS		25.06	-77.34	227940
Nasugbu	PH		14.07	120.63	62857
Nasushiobara	JP		36.98	140.07	115794
Nasīm Shahr	IR		35.57	51.16	200393
Nasīrābād	IN		26.30	74.73	51747
Natal	BR		-5.79	-35.21	896708
Natchez	US	Mississippi	31.56	-91.40	15128
Natchitoches	US	Louisiana	31.76	-93.09	18365
Natick	US	Massachusetts	42.28	-71.35	32276
National City	US	California	32.68	-117.10	61060
Natitingou	BJ		10.30	1.38	53284
Natore	BD		24.41	88.99	369138
Natori-shi	JP		38.17	140.88	78718
Naucalpan de Juárez	MX		19.48	-99.24	834434
Naugatuck	US	Connecticut	41.49	-73.05	31538
Navadwīp	IN		23.41	88.37	111123
Navan	IE		53.65	-6.68	33886
Navarre	US	Florida	30.40	-86.86	31378
Navegantes	AO		-12.59	13.39	240075
Navegantes	BR		-26.90	-48.65	86401
Navi Mumbai	IN		19.04	73.02	2600000
Naviraí	BR		-23.07	-54.19	50457
Navoiy	UZ		40.08	65.38	144158
Navojoa	MX		27.07	-109.44	113836
Navotas	PH		14.67	120.95	249463
Navsari	IN		20.94	72.92	171109
Nawabshah	PK		26.24	68.40	363138
Nawalgarh	IN		27.85	75.27	63948
Nawābganj	BD		24.59	88.27	142361
Nawābganj	IN		26.93	81.20	79246
Nawāda	IN		24.89	85.54	98029
Naxi	CN		28.77	105.36	50020
Naxçıvan	AZ		39.21	45.41	97200
Nay Pyi Taw	MM		19.75	96.13	925000
Naya Gaon	IN		30.78	76.79	50869
Nazareth	IL		32.70	35.30	77445
Nazarovo	RU		56.01	90.42	55252
Nazilli	TR		37.92	28.32	119370
Nazran	RU		43.23	44.77	164131
Nazrēt	ET		8.55	39.27	456900
Naz̧arābād	IR		35.95	50.61	213388
Nchelenge	ZM		-9.35	28.73	77746
Ndola	ZM		-12.96	28.64	627503
Near North Side	US	Illinois	41.90	-87.63	85711
Near South Side	US	Illinois	41.86	-87.62	22401
Neath	GB		51.66	-3.80	46126
Necochea	AR		-38.55	-58.74	73557
Nederland	US	Texas	29.97	-93.99	17196
Nedumangād	IN		8.60	77.00	60161
Needham	US	Massachusetts	42.28	-71.23	28886
Neelankarai	IN		12.95	80.26	76600
Neenah	US	Wisconsin	44.19	-88.46	25792
Neftekamsk	RU		56.09	54.26	126805
Nefteyugansk	RU		61.10	72.60	112632
Negage	AO		-7.76	15.27	92950
Negara	ID		-8.36	114.62	100074
Negombo	LK		7.21	79.84	137223
Negēlē	ET		5.32	39.58	73100
Nehe	CN		48.48	124.87	108253
Neihu	TW		25.08	121.59	274538
Neijiang	CN		29.58	105.06	1251095
Neili	TW		24.97	121.26	112845
Neiva	CO		2.93	-75.28	357392
Nekā	IR		36.65	53.30	60991
Nek’emtē	ET		9.08	36.55	156000
Nellore	IN		14.45	79.99	547621
Nelson	NZ		-41.27	173.28	54400
Nelson	GB		53.83	-2.20	29317
Nemby	PY		-25.39	-57.54	94641
Nenjiang	CN		49.17	125.22	87236
Nepalgunj	NP		28.05	81.62	166258
Nepean	CA		45.34	-75.72	180000
Nerang	AU		-27.99	153.34	16739
Nerkunram	IN		13.06	80.21	59790
Nerupperichchal	IN		11.16	77.37	53579
Neryungri	RU		56.66	124.72	66320
Ness Ziona	IL		31.93	34.80	50351
Neston	GB		51.41	-2.20	15352
Neston	GB		53.28	-3.05	15064
Netanya	IL		32.33	34.86	228204
Nether Edge	GB		53.36	-1.49	18890
Netrakona	BD		24.88	90.73	79016
Neu-Hohenschönhausen	DE		52.57	13.51	56921
Neu-Ulm	DE		48.39	10.01	51389
Neubrandenburg	DE		53.56	13.26	68082
Neubrück	DE		51.13	6.64	51109
Neue Neustadt	DE		52.15	11.63	226851
Neufchâtel-Est–Lebourgneuf	CA		46.85	-71.34	37540
Neuilly-sur-Seine	FR		48.88	2.27	61300
Neukölln	DE		52.48	13.43	164636
Neumünster	DE		54.07	9.98	80196
Neuquén	AR		-38.95	-68.06	231198
Neuss	DE		51.20	6.69	152457
Neustadt an der Weinstraße	DE		49.35	8.14	53984
Neuwied	DE		50.43	7.47	66805
Nevinnomyssk	RU		44.63	41.94	134345
Nevşehir	TR		38.62	34.71	75527
New Albany	US	Indiana	38.29	-85.82	36732
New Bedford	US	Massachusetts	41.64	-70.93	101079
New Berlin	US	Wisconsin	42.98	-88.11	39825
New Bern	US	North Carolina	35.11	-77.04	30070
New Braunfels	US	Texas	29.70	-98.12	70543
New Brighton	US	Minnesota	45.07	-93.20	22351
New Britain	US	Connecticut	41.66	-72.78	72808
New Brunswick	US	New Jersey	40.49	-74.45	57035
New Cairo	EG		30.03	31.47	313139
New Canaan	US	Connecticut	41.15	-73.49	19738
New Caney	US	Texas	30.16	-95.21	20000
New Castle	US	Pennsylvania	41.00	-80.35	22375
New Castle	US	Indiana	39.93	-85.37	17621
New City	US	Illinois	41.81	-87.66	40997
New City	US	New York	41.15	-73.99	33559
New Cross	GB		51.48	-0.04	15756
New Delhi	IN		28.62	77.21	317797
New Glasgow	CA		45.58	-62.65	18665
New Halfa	SD		15.33	35.60	63589
New Haven	US	Connecticut	41.31	-72.93	130322
New Haven	US	Indiana	41.07	-85.01	15709
New Hope	US	Minnesota	45.04	-93.39	21032
New Iberia	US	Louisiana	30.00	-91.82	30754
New Kingston	JM		18.01	-76.78	583958
New Lenox	US	Illinois	41.51	-87.97	25800
New London	US	Connecticut	41.36	-72.10	27179
New Lynn	NZ		-36.91	174.69	23800
New Malden	GB		51.40	-0.26	23818
New Milford	US	New Jersey	40.94	-74.02	16801
New Mills	GB		53.37	-2.00	17968
New Milton	GB		50.76	-1.67	25546
New Mirpur City	PK		33.15	73.75	124352
New Orleans	US	Louisiana	29.95	-90.08	362701
New Philadelphia	US	Ohio	40.49	-81.45	17484
New Plymouth	NZ		-39.07	174.08	90100
New Port Richey	US	Florida	28.24	-82.72	15842
New Rochelle	US	New York	40.91	-73.78	79846
New Smyrna Beach	US	Florida	29.03	-80.93	24298
New South Memphis	US	Tennessee	35.09	-90.06	641608
New Springville	US	New York	40.59	-74.16	20756
New Taipei City	TW		25.06	121.46	4004367
New Territories	HK		22.42	114.11	3984077
New Territory	US	Texas	29.59	-95.68	15186
New Westminster	CA		49.21	-122.91	78916
New York City	US	New York	40.71	-74.01	8804190
Newark	US	New Jersey	40.74	-74.17	281944
Newark	US	Ohio	40.06	-82.40	47986
Newark	US	California	37.53	-122.04	45336
Newark	US	Delaware	39.68	-75.75	33817
Newark on Trent	GB		53.07	-0.82	43363
Newberg	US	Oregon	45.30	-122.97	22780
Newburg	US	Kentucky	38.16	-85.66	19967
Newburgh	US	New York	41.50	-74.01	28290
Newburn	GB		54.99	-1.74	41347
Newbury	GB		51.40	-1.32	33065
Newburyport	US	Massachusetts	42.81	-70.88	17982
Newcastle	AU		-32.93	151.78	508437
Newcastle	ZA		-27.76	29.93	404838
Newcastle under Lyme	GB		53.00	-2.23	127727
Newcastle upon Tyne	GB		54.97	-1.61	300125
Newington	US	Connecticut	41.70	-72.72	30562
Newmarket	CA		44.05	-79.47	91034
Newmarket	GB		52.24	0.40	20384
Newnan	US	Georgia	33.38	-84.80	37291
Newport	GB		51.59	-3.00	161506
Newport	GB		50.70	-1.29	24884
Newport	US	Rhode Island	41.49	-71.31	24232
Newport	US	Kentucky	39.09	-84.50	15354
Newport Beach	US	California	33.62	-117.93	87127
Newport News	US	Virginia	36.98	-76.43	186247
Newport Pagnell	GB		52.09	-0.72	15067
Newquay	GB		50.42	-5.07	20189
Newry	GB		54.18	-6.34	27757
Newton	CA		49.13	-122.85	159390
Newton	US	Massachusetts	42.34	-71.21	88817
Newton	US	Kansas	38.05	-97.35	19216
Newton	US	Iowa	41.70	-93.05	15125
Newton Abbot	GB		50.53	-3.61	36474
Newton Aycliffe	GB		54.62	-1.57	26415
Newton Mearns	GB		55.77	-4.33	28210
Newton-le-Willows	GB		53.45	-2.60	24642
Newtonbrook East	CA		43.79	-79.41	16097
Newtonbrook West	CA		43.79	-79.43	23831
Newtownabbey	GB		54.66	-5.91	63860
Newtownards	GB		54.59	-5.69	29363
Neyagawa	JP		34.77	135.63	238549
Neyshābūr	IR		36.21	58.80	220929
Neyveli	IN		11.61	79.50	179150
Neyyāttinkara	IN		8.40	77.09	88104
Nganjuk	ID		-7.61	111.90	69011
Ngaoundéré	CM		7.33	13.58	238196
Nghi Sơn	VN		19.33	105.82	302210
Nghi Xuân	VN		18.66	105.75	118000
Nghĩa Lộ	VN		21.60	104.52	68206
Nghĩa Đô	VN		21.05	105.80	96418
Ngong	KE		-1.35	36.67	102323
Ngozi	BI		-2.91	29.83	61716
Nguru	NG		12.88	10.46	111014
Ngã Bảy	VN		9.81	105.82	101192
Ngã Năm	VN		9.57	105.60	58588
Nha Trang	VN		12.25	109.19	579000
NIA Valencia	PH		7.91	125.09	223620
Niagara	CA		43.64	-79.41	31180
Niagara Falls	CA		43.10	-79.07	99818
Niagara Falls	US	New York	43.09	-79.06	48916
Niagara-on-the-Lake	CA		43.26	-79.09	17511
Niamey	NE		13.51	2.11	1323691
Nianbo	CN		36.48	102.42	260184
Nianzhuang	CN		34.30	117.77	80617
Nianzishan	CN		47.51	122.89	62131
Nice	FR		43.70	7.27	342669
Nicetown-Tioga	US	Pennsylvania	40.01	-75.16	17382
Nichinan	JP		31.60	131.37	51241
Nicholasville	US	Kentucky	37.88	-84.57	29754
Nicolás Romero	MX		19.64	-99.31	281799
Nicosia	CY		35.17	33.35	200452
Nieuwegein	NL		52.03	5.08	61489
Nigel	ZA		-26.43	28.48	140644
Nigg	GB		57.12	-2.09	16400
Nihommatsu	JP		37.58	140.43	53557
Niigata	JP		37.92	139.04	797591
Niihama	JP		33.96	133.31	123059
Niitsu-honchō	JP		37.80	139.12	65910
Niiza	JP		35.82	139.56	166017
Nijmegen	NL		51.84	5.85	177359
Nikki	BJ		9.94	3.21	66109
Nikkō	JP		36.75	139.62	77661
Nikol’skoye	RU		55.68	37.48	50000
Nikopol	UA		47.57	34.39	105160
Nikšić	ME		42.77	18.94	58212
Niles	US	Illinois	42.02	-87.80	29876
Niles	US	Ohio	41.18	-80.77	18651
Nilópolis	BR		-22.81	-43.41	147281
Nilüfer	TR		40.21	28.92	536365
Nimach	IN		24.46	74.87	128561
Ningbo	CN		29.88	121.55	3731203
Ningde	CN		26.66	119.52	429260
Ninghai	CN		29.29	121.42	68330
Ninghai	CN		37.38	121.61	56937
Ningyang	CN		35.76	116.79	82994
Ning’er	CN		23.04	101.04	162711
Ninh Hòa	VN		12.49	109.12	230566
Nioki	CD		-2.72	17.69	62153
Nioko I	BF		12.40	-1.44	65263
Niono	ML		14.25	-5.99	52584
Nioro	ML		15.23	-9.59	51933
Niort	FR		46.32	-0.46	54660
Nipomo	US	California	35.04	-120.48	16714
Nippes	DE		50.97	6.95	113487
Nipāni	IN		16.40	74.38	62865
Nirgua	VE		10.15	-68.56	54080
Nirmal	IN		19.10	78.34	88433
Nishi-Tokyo-shi	JP		35.73	139.54	207388
Nishinomiya	JP		34.72	135.33	485587
Nishio	JP		34.87	137.05	169984
Nisshin	JP		35.14	137.05	91795
Niterói	BR		-22.88	-43.10	456456
Nithari	IN		28.70	77.05	50464
Nitra	SK		48.31	18.08	86329
Niu Valley	US	Hawaii	21.28	-157.74	19250
Nixa	US	Missouri	37.04	-93.29	20984
Nizhnekamsk	RU		55.64	51.82	234297
Nizhnevartovsk	RU		60.93	76.55	244937
Nizhniy Novgorod	RU		56.33	44.00	1259013
Nizhny Tagil	RU		57.92	59.97	381116
Nizhyn	UA		51.05	31.89	66983
Nizip	TR		37.01	37.79	82308
Nizwá	OM		22.93	57.53	72076
Nizāmābād	IN		18.67	78.10	311152
Niğde	TR		37.97	34.68	91039
Niš	RS		43.32	21.90	250000
Njeru	UG		0.44	33.18	178800
Njombe	TZ		-9.35	34.77	92537
Nkayi	CG		-4.18	13.29	103000
Nkongsamba	CM		4.95	9.94	162309
Nkowakowa	ZA		-23.89	30.29	51350
Nkpor	NG		6.15	6.83	103733
Nkwerre	NG		5.76	7.10	62973
Nnewi	NG		6.02	6.92	193987
Nobeoka	JP		32.58	131.67	119521
Noble Park	AU		-37.97	145.17	30921
Noblesville	US	Indiana	40.05	-86.01	59093
Noda	JP		35.95	139.87	154114
Noe Valley	US	California	37.75	-122.43	22893
Nogales	MX		31.31	-110.94	264782
Nogales	US	Arizona	31.34	-110.93	20252
Noginsk	RU		55.86	38.45	115979
Noida	IN		28.58	77.33	293908
Noisy-le-Grand	FR		48.85	2.56	62420
Nokha	IN		27.56	73.47	62699
NoMa	US	District of Columbia	38.90	-77.01	20700
Nong Chok	TH		13.86	100.86	157138
Nong Khaem	TH		13.71	100.35	150218
Nong Khai	TH		17.88	102.74	63609
Nonoichi	JP		36.53	136.62	57238
Nor Nork	AM		40.20	44.57	137300
Norbury	GB		51.42	-0.12	16476
Norco	US	California	33.93	-117.55	26289
Norcross	US	Georgia	33.94	-84.21	16634
Norderstedt	DE		53.70	9.99	82844
Nordhorn	DE		52.43	7.07	52803
Norfolk	US	Virginia	36.85	-76.29	238005
Norfolk	US	Nebraska	42.03	-97.42	24366
Norfolk County	CA		42.83	-80.38	60847
Norilsk	RU		69.35	88.20	140800
Norland	US	Florida	25.95	-80.21	23604
Normal	US	Illinois	40.51	-88.99	54373
Norman	US	Oklahoma	35.22	-97.44	128026
Norris Green	GB		53.45	-2.92	19610
Norristown	US	Pennsylvania	40.12	-75.34	34412
Norrköping	SE		58.59	16.18	93765
North Amityville	US	New York	40.70	-73.43	17862
North Andover	US	Massachusetts	42.70	-71.14	28222
North Arlington	US	New Jersey	40.79	-74.13	15904
North Attleborough Center	US	Massachusetts	41.97	-71.32	16796
North Augusta	US	South Carolina	33.50	-81.97	22522
North Aurora	US	Illinois	41.81	-88.33	17456
North Babylon	US	New York	40.72	-73.32	17509
North Battleford	CA		52.78	-108.30	19440
North Bay	CA		46.32	-79.47	50396
North Bay Shore	US	New York	40.75	-73.26	18944
North Bel Air	US	Maryland	39.54	-76.35	33925
North Bellmore	US	New York	40.69	-73.53	19941
North Bergen	US	New Jersey	40.80	-74.01	63484
North Bethesda	US	Maryland	39.04	-77.12	43828
North Brunswick	US	New Jersey	40.45	-74.48	43905
North Canton	US	Ohio	40.88	-81.40	17441
North Center	US	Illinois	41.95	-87.68	34623
North Charleston	US	South Carolina	32.85	-79.97	108304
North Chicago	US	Illinois	42.33	-87.84	29491
North Chicopee	US	Massachusetts	42.18	-72.60	55179
North Cowichan	CA		48.84	-123.69	29676
North Creek	US	Washington	47.82	-122.18	26410
North Decatur	US	Georgia	33.79	-84.31	16698
North Delta	CA		49.17	-122.92	60769
North Druid Hills	US	Georgia	33.82	-84.31	18947
North Fort Myers	US	Florida	26.67	-81.88	39407
North Haven	US	Connecticut	41.39	-72.86	24093
North Highlands	US	California	38.69	-121.37	42694
North Hills	US	California	34.24	-118.48	56946
North Hollywood	US	California	34.17	-118.38	64587
North Kingstown	US	Rhode Island	41.55	-71.47	28042
North La Crosse	US	Wisconsin	43.85	-91.25	50470
North Lakes	AU		-27.22	153.02	21260
North Lakhimpur	IN		27.24	94.10	59841
North Las Vegas	US	Nevada	36.20	-115.12	234807
North Lauderdale	US	Florida	26.22	-80.23	43703
North Lawndale	US	Illinois	41.86	-87.72	35276
North Liberty	US	Iowa	41.75	-91.60	15931
North Little Rock	US	Arkansas	34.77	-92.27	66504
North Massapequa	US	New York	40.70	-73.46	17886
North Melbourne	AU		-37.80	144.95	15395
North Miami	US	Florida	25.89	-80.19	62435
North Miami Beach	US	Florida	25.93	-80.16	43971
North Myrtle Beach	US	South Carolina	33.82	-78.68	15579
North Ogden	US	Utah	41.31	-111.96	18446
North Olmsted	US	Ohio	41.42	-81.92	32004
North Peoria	US	Illinois	40.72	-89.58	113004
North Plainfield	US	New Jersey	40.63	-74.43	22140
North Platte	US	Nebraska	41.12	-100.77	24194
North Port	US	Florida	27.04	-82.24	62345
North Potomac	US	Maryland	39.08	-77.26	24410
North Providence	US	Rhode Island	41.85	-71.47	33835
North Richland Hills	US	Texas	32.83	-97.23	69204
North Ridgeville	US	Ohio	41.39	-82.02	32483
North Royalton	US	Ohio	41.31	-81.72	30311
North Salt Lake	US	Utah	40.85	-111.91	19796
North Shields	GB		55.02	-1.45	39747
North Shore	NZ		-36.80	174.75	258697
North St.James Town	CA		43.67	-79.38	18615
North Stamford	US	Connecticut	41.14	-73.54	121230
North Tonawanda	US	New York	43.04	-78.86	30785
North Tustin	US	California	33.76	-117.79	24917
North Valley Stream	US	New York	40.69	-73.70	16628
North Vancouver	CA		49.32	-123.07	88168
North Watford	GB		51.68	-0.39	33000
Northallerton	GB		54.34	-1.43	16832
Northampton	GB		52.25	-0.88	245899
Northampton	US	Massachusetts	42.33	-72.64	28540
Northbrook	US	Illinois	42.13	-87.83	33663
Northcote	AU		-37.77	145.00	25276
Northdale	US	Florida	28.09	-82.51	22079
Northfield	US	Minnesota	44.46	-93.16	20380
Northglenn	US	Colorado	39.89	-104.99	39197
Northolt	GB		51.55	-0.37	26000
Northport	US	Alabama	33.23	-87.58	24772
Northridge	US	California	34.23	-118.54	68469
Northwest One	US	District of Columbia	38.90	-77.01	23386
Northwich	GB		53.26	-2.52	47421
Northwood	US	California	33.71	-117.76	22218
Norton	ZW		-17.88	30.70	87039
Norton	US	Massachusetts	41.97	-71.19	19808
Norton Shores	US	Michigan	43.17	-86.26	24208
Norwalk	US	California	33.90	-118.08	107140
Norwalk	US	Connecticut	41.12	-73.41	88485
Norwalk	US	Ohio	41.24	-82.62	16827
Norwich	GB		52.63	1.30	143135
Norwich	US	Connecticut	41.52	-72.08	39899
Norwood	US	Massachusetts	42.19	-71.20	28602
Norwood	US	Ohio	39.16	-84.46	19915
Norzagaray	PH		14.91	121.05	140697
Noshiro	JP		40.21	140.03	52283
Nossa Senhora de Fátima	CN		22.21	113.55	126000
Nossa Senhora do Socorro	BR		-10.86	-37.13	192330
Notre-Dame-de-Grâce	CA		45.48	-73.61	68152
Notting Hill	GB		51.51	-0.21	21000
Nottingham	GB		52.95	-1.15	323632
Nou Barris	ES		41.44	2.18	166310
Nouadhibou	MR		20.94	-17.04	146048
Nouakchott	MR		18.09	-15.98	1184530
Nouméa	NC		-22.27	166.45	93060
Nova Friburgo	BR		-22.28	-42.53	191158
Nova Iguaçu	BR		-22.76	-43.45	843046
Nova Lima	BR		-19.99	-43.85	111697
Nova Mutum	BR		-13.83	-56.08	61223
Nova Odessa	BR		-22.78	-47.30	62019
Nova Serrana	BR		-19.88	-44.98	105552
Nova Vida	AO		-8.91	13.22	464985
Novara	IT		45.45	8.62	101916
Novato	US	California	38.11	-122.57	55530
Novaya Balakhna	RU		56.49	43.60	63083
Novena	SG		1.32	103.84	53160
Novi	US	Michigan	42.48	-83.48	58723
Novi Pazar	RS		43.14	20.51	85996
Novi Sad	RS		45.25	19.84	215400
Novo Gama	BR		-16.06	-48.04	103804
Novo Hamburgo	BR		-29.68	-51.13	253841
Novo Repartimento	BR		-4.33	-49.80	60732
Novo-Peredelkino	RU		55.65	37.34	115536
Novoaltaysk	RU		53.41	83.94	61050
Novocheboksarsk	RU		56.11	47.48	128468
Novocherkassk	RU		47.42	40.09	166974
Novogireyevo	RU		55.75	37.82	95000
Novokhovrino	RU		55.87	37.50	50000
Novokuybyshevsk	RU		53.10	49.94	111800
Novokuznetsk	RU		53.76	87.14	539616
Novokuz’minki	RU		55.72	37.78	50000
Novomoskovsk	RU		54.01	38.29	130982
Novopolotsk	BY		55.53	28.59	95370
Novorossiysk	RU		44.73	37.76	241856
Novoshakhtinsk	RU		47.76	39.93	99478
Novosibirsk	RU		55.02	82.93	1612833
Novotroitsk	RU		51.20	58.31	106186
Novoural’sk	RU		57.25	60.09	93849
Novovladykino	RU		55.85	37.58	50000
Novozavodskyi	UA		51.49	31.26	179600
Novyy Urengoy	RU		66.08	76.63	94212
Novyye Cherëmushki	RU		55.70	37.58	101000
Novyye Kuz’minki	RU		55.70	37.75	143000
Nowrangapur	IN		19.23	82.55	1220946
Nowshera Kalan	PK		34.02	71.97	88003
Nowy Sącz	PL		49.62	20.70	84376
Noyabrsk	RU		63.19	75.44	110000
Nsukka	NG		6.86	7.40	111017
Ntoum	GA		0.39	9.76	62445
Ntuzuma	ZA		-29.74	30.95	125394
Nueva Guinea	NI		11.69	-84.46	52929
Nuevitas	CU		21.54	-77.26	54022
Nuevo Casas Grandes	MX		30.42	-107.91	55553
Nuevo Laredo	MX		27.48	-99.52	416055
Nukus	UZ		42.46	59.61	332500
Numan	NG		9.46	12.03	77617
Numazu	JP		35.10	138.87	189486
Nuneaton	GB		52.52	-1.47	88813
Nungua	GH		5.60	-0.08	70483
Nunukan	ID		4.14	117.65	67006
Nuremberg	DE		49.45	11.08	515543
Nusaybin	TR		37.07	41.21	88977
Nutana Sector	CA		52.10	-106.64	72564
Nutley	US	New Jersey	40.82	-74.16	27572
Nuuanu - Punchbowl	US	Hawaii	21.34	-157.83	16205
Nuuk	GL		64.18	-51.72	14798
Nyagan	RU		62.14	65.39	52137
Nyagatare	RW		-1.30	30.32	100000
Nyala	SD		12.05	24.88	565734
Nyaunglebin	MM		17.95	96.72	89626
Nyeri	KE		-0.42	36.95	80081
Nyingchi	CN		29.65	94.36	200000
Nyunzu	CD		-5.96	28.02	62565
Nyvky	UA		50.46	30.41	71700
Nyzhnodniprovsk	UA		48.48	35.12	160123
Nyíregyháza	HU		47.96	21.72	117689
Nzagi	AO		-8.39	15.30	60000
Nzega	TZ		-4.22	33.18	125193
Nzérékoré	GN		7.76	-8.82	226426
Néa Ionía	GR		38.04	23.76	67134
Néa Smýrni	GR		37.95	23.71	73076
Néma	MR		16.62	-7.26	60000
Níkaia	GR		37.97	23.65	89380
Nîmes	FR		43.84	4.36	148236
Núi Thành	VN		15.43	108.66	69406
Nābha	IN		30.38	76.15	67972
Nāgarpur	BD		24.06	89.88	238422
Nāgaur	IN		27.20	73.73	105218
Nāgercoil	IN		8.18	77.43	224849
Nāmakkal	IN		11.22	78.17	55997
Nāngloi Jāt	IN		28.68	77.07	205596
Nāyf	AE		25.27	55.30	53075
Nāḩiyat al Iskandarīyah	IQ		32.89	44.35	100600
Nīmbāhera	IN		24.62	74.68	61949
Nōgata	JP		33.74	130.72	56821
Nūrābād	IR		34.07	47.97	65547
Nūrābād	IR		30.11	51.52	57058
Nūzvīd	IN		16.79	80.85	58590
O'Connor-Parkview	CA		43.71	-79.31	18675
O'Fallon	US	Missouri	38.81	-90.70	85040
O'Fallon	US	Illinois	38.59	-89.91	29002
Oadby	GB		52.61	-1.08	23849
Oak Bay	CA		48.45	-123.30	18015
Oak Creek	US	Wisconsin	42.89	-87.86	35243
Oak Forest	US	Illinois	41.60	-87.74	28074
Oak Grove	US	Oregon	45.42	-122.64	16629
Oak Harbor	US	Washington	48.29	-122.64	22693
Oak Hill	US	Virginia	38.93	-77.40	33811
Oak Lawn	US	Illinois	41.71	-87.76	56781
Oak Park	US	Illinois	41.89	-87.78	52287
Oak Park	US	Michigan	42.46	-83.18	29752
Oak Ridge	US	Tennessee	36.01	-84.27	29302
Oak Ridge	US	Florida	28.47	-81.42	22685
Oakdale	US	Minnesota	44.96	-92.96	28080
Oakdale	US	California	37.77	-120.85	22259
Oakland	US	California	37.80	-122.27	419267
Oakland Park	US	Florida	26.17	-80.13	44319
Oakleaf Plantation	US	Florida	30.17	-81.84	20315
Oakley	US	California	38.00	-121.71	39813
Oakton	US	Virginia	38.88	-77.30	34166
Oakville	CA		43.45	-79.68	213759
Oakville	US	Missouri	38.47	-90.30	36143
Oakwood Village	CA		43.68	-79.44	21210
Oas	PH		13.26	123.50	64890
Oaxaca	MX		17.06	-96.73	255029
Obalende	NG		6.45	3.42	342000
Obando	PH		14.71	120.94	59929
Oberhausen	DE		51.48	6.86	219176
Oberá	AR		-27.49	-55.12	56528
Obihiro	JP		42.92	143.20	166536
Obninsk	RU		55.11	36.61	107392
Obolon	UA		50.51	30.51	239500
Obonoma	NG		4.71	6.79	68584
Obra	IN		24.42	82.99	56110
Obruchevo	RU		55.66	37.52	85616
Obuase	GH		6.20	-1.67	179604
Ocala	US	Florida	29.19	-82.14	58218
Ocaña	CO		8.24	-73.36	101158
Ocean Acres	US	New Jersey	39.74	-74.28	16142
Ocean Springs	US	Mississippi	30.41	-88.83	17636
Oceanside	US	California	33.20	-117.38	175691
Oceanside	US	New York	40.64	-73.64	32109
Ochakovo-Matveyevskoye	RU		55.68	37.45	114000
Ochota	PL		52.22	20.99	82774
Ocoee	US	Florida	28.57	-81.54	43608
Oconomowoc	US	Wisconsin	43.11	-88.50	16360
Ocotlán	MX		20.35	-102.77	83769
Ocumare del Tuy	VE		10.12	-66.78	166072
Odawara	JP		35.26	139.16	188856
Ode	NG		7.79	5.71	75463
Odendaalsrus	ZA		-27.87	26.69	76371
Odense	DK		55.40	10.39	180863
Odenton	US	Maryland	39.08	-76.70	37132
Odesa	UA		46.49	30.74	1010537
Odessa	US	Texas	31.85	-102.37	114428
Odienné	CI		9.51	-7.56	54669
Odintsovo	RU		55.67	37.28	137041
Odivelas	PT		38.79	-9.18	54624
Offa	NG		8.15	4.72	113830
Offenbach	DE		50.10	8.77	119192
Offenburg	DE		48.47	7.94	59238
Officer	AU		-38.06	145.41	18503
Ogaminana	NG		7.59	6.22	84373
Ogbomoso	NG		8.13	4.24	433030
Ogden	US	Utah	41.22	-111.97	85444
Ogōri	JP		33.39	130.55	59360
Ohafia-Ifigh	NG		5.61	7.81	73355
Oildale	US	California	35.42	-119.02	32684
Ojo de Agua	MX		19.68	-99.01	386290
Ojus	US	Florida	25.95	-80.15	18036
Okanagan Mission	CA		49.82	-119.48	38374
Okara	PK		30.81	73.45	533693
Okaya	JP		36.06	138.05	54286
Okayama	JP		34.65	133.93	724691
Okazaki	JP		34.95	137.17	384654
Okcheon	KR		36.30	127.57	56634
Oke Mesi	NG		7.82	4.92	79563
Okegawa	JP		36.00	139.56	75062
Okemos	US	Michigan	42.72	-84.43	21369
Okene	NG		7.55	6.24	479178
Okha	IN		22.47	69.07	62052
Okigwe	NG		5.83	7.35	115499
Okinawa	JP		26.34	127.80	142752
Oklahoma City	US	Oklahoma	35.47	-97.52	681054
Okolona	US	Kentucky	38.14	-85.69	17134
Okotoks	CA		50.73	-113.98	30214
Okrika	NG		4.74	7.08	133271
Oktyabrsky	RU		54.48	53.47	108200
Olanchito	HN		15.48	-86.57	124286
Olathe	US	Kansas	38.88	-94.82	134305
Olavarría	AR		-36.89	-60.32	89721
Olbia	IT		40.92	9.50	60345
Old Bridge	US	New Jersey	40.41	-74.37	23753
Old Jamestown	US	Missouri	38.83	-90.29	19184
Old Swan	GB		53.41	-2.91	15596
Old Trafford	GB		53.46	-2.29	21447
Oldenburg	DE		53.14	8.21	159218
Oldham	GB		53.54	-2.12	237110
Oleksandrivskyi	UA		47.97	37.80	100330
Oleksandriya	UA		48.67	33.12	76097
Oleksiyivka	UA		50.05	36.19	100500
Olinda	BR		-8.01	-34.86	366754
Olive Branch	US	Mississippi	34.96	-89.83	36010
Olmaliq	UZ		40.84	69.60	133400
Olney	US	Pennsylvania	40.04	-75.12	39154
Olney	US	Maryland	39.15	-77.07	33844
Olomouc	CZ		49.60	17.25	99496
Olongapo	PH		14.83	120.28	221178
Olsztyn	PL		53.78	20.49	169793
Oltinko‘l	UZ		43.07	58.90	59122
Olupona	NG		7.60	4.19	95002
Olympia	US	Washington	47.04	-122.90	55733
Olímpia	BR		-20.74	-48.91	55074
Omagh	GB		54.60	-7.30	21056
Omaha	US	Nebraska	41.26	-95.94	486051
Omdurman	SD		15.64	32.48	1849659
Omoa	HN		15.78	-88.04	58172
Omsk	RU		54.99	73.37	1172070
Omīdīyeh	IR		30.76	49.70	67427
Onalaska	US	Wisconsin	43.88	-91.24	18468
Ondjiva	AO		-17.07	15.73	121537
Ondo	NG		7.09	4.84	375000
Ongata Rongai	KE		-1.40	36.76	172569
Ongjin	KP		37.93	125.36	64247
Ongole	IN		15.50	80.04	208344
Onitsha	NG		6.15	6.79	1553000
Onomichi	JP		34.42	133.20	131170
Ontario	US	California	34.06	-117.65	171214
Oosterhout	NL		51.65	4.86	53107
Ooty	IN		11.41	76.70	233426
Opa-locka	US	Florida	25.90	-80.25	16565
Opava	CZ		49.94	17.90	60252
Opelika	US	Alabama	32.65	-85.38	29527
Opelousas	US	Louisiana	30.53	-92.08	16591
Opole	PL		50.67	17.93	127676
Opportunity	US	Washington	47.65	-117.24	25877
Oradea	RO		47.05	21.92	183105
Orai	IN		25.99	79.45	158265
Oral	KZ		51.25	51.43	330000
Oran	DZ		35.70	-0.64	803329
Orange	US	California	33.79	-117.85	140992
Orange	AU		-33.28	149.10	41920
Orange	US	New Jersey	40.77	-74.23	34457
Orange	US	Texas	30.09	-93.74	19347
Orangevale	US	California	38.68	-121.23	33960
Orangeville	CA		43.92	-80.10	30734
Oranjestad	AW		12.52	-70.03	29998
Orchards	US	Washington	45.67	-122.56	19556
Orcutt	US	California	34.87	-120.44	28905
Ordos	CN		39.61	109.78	1940653
Ordu	TR		40.98	37.89	229214
Oregon	US	Ohio	41.64	-83.49	20102
Oregon City	US	Oregon	45.36	-122.61	35831
Orekhovo-Borisovo	RU		55.61	37.73	144000
Orekhovo-Borisovo Severnoye	RU		55.62	37.68	128000
Orekhovo-Zuyevo	RU		55.81	38.99	120000
Orem	US	Utah	40.30	-111.69	94457
Orenburg	RU		51.77	55.10	564773
Orhangazi	TR		40.49	29.31	51792
Orient Heights	US	Massachusetts	42.39	-71.00	15741
Orihuela	ES		38.08	-0.94	101321
Orillia	CA		44.61	-79.42	31166
Orinda	US	California	37.88	-122.18	19279
Orion	PH		14.62	120.58	63044
Orita-Eruwa	NG		7.56	3.44	71027
Orito	CO		0.67	-76.87	57774
Oriximiná	BR		-1.77	-55.87	68294
Orizaba	MX		18.85	-97.10	123182
Orkney	ZA		-26.98	26.67	110052
Orland Park	US	Illinois	41.63	-87.85	58619
Orlando	US	Florida	28.54	-81.38	334854
Orléans	CA		45.46	-75.50	125937
Orléans	FR		47.90	1.90	116344
Ormoc	PH		11.01	124.61	238545
Ormond Beach	US	Florida	29.29	-81.06	40970
Ormskirk	GB		53.57	-2.88	24073
Oro Valley	US	Arizona	32.39	-110.97	45303
Oroqen Zizhiqi	CN		50.57	123.72	61582
Oroquieta	PH		8.49	123.80	71373
Oroville	US	California	39.51	-121.56	16260
Orpington	GB		51.37	0.10	15248
Orsha	BY		54.51	30.40	101662
Orsk	RU		51.23	58.49	246836
Oruro	BO		-17.97	-67.09	208684
Orël	RU		52.97	36.08	303696
Orūmīyeh	IR		37.55	45.08	577307
Osaka	JP		34.69	135.50	2753862
Osan	KR		37.15	127.07	238788
Osasco	BR		-23.53	-46.79	728615
Osh	KG		40.53	72.80	322164
Oshawa	CA		43.90	-78.85	175383
Oshkosh	US	Wisconsin	44.02	-88.54	66555
Oshnavīyeh	IR		37.04	45.10	50661
Oshodi	NG		6.56	3.34	170870
Osijek	HR		45.55	18.69	75535
Oslo	NO		59.91	10.75	1082575
Osmaniye	TR		37.07	36.25	202837
Osnabrück	DE		52.27	8.05	166462
Osogbo	NG		7.77	4.56	645000
Osorno	CL		-40.57	-73.13	135773
Oss	NL		51.77	5.52	76430
Ossett	GB		53.68	-1.58	21861
Ossining	US	New York	41.16	-73.86	25441
Ostankinskiy	RU		55.83	37.62	60000
Ostend	BE		51.22	2.93	69011
Ostrava	CZ		49.83	18.28	279791
Ostrowiec Świętokrzyski	PL		50.93	21.39	73989
Ostrołęka	PL		53.09	21.58	53740
Ostrów Wielkopolski	PL		51.66	17.81	72898
Ostuncalco	GT		14.87	-91.62	51828
Oswego	US	Illinois	41.68	-88.35	33955
Oswego	US	New York	43.46	-76.51	17787
Oswestry	GB		52.86	-3.05	18743
Ota	NG		6.69	3.23	251546
Otahuhu	NZ		-36.94	174.84	17780
Otara	NZ		-36.95	174.87	24420
Otaru	JP		43.19	141.00	115333
Otradnyy	RU		53.38	51.35	50127
Otsego	US	Minnesota	45.27	-93.59	15551
Ottakring	AT		48.22	16.30	104627
Ottapalam	IN		10.77	76.38	53792
Ottawa	CA		45.41	-75.70	1017449
Ottawa	US	Illinois	41.35	-88.84	18342
Ottawa South	CA		45.39	-75.69	125090
Ottumwa	US	Iowa	41.02	-92.41	24624
Ouagadougou	BF		12.37	-1.53	2415266
Ouahigouya	BF		13.58	-2.42	124587
Ouargla	DZ		31.95	5.33	169928
Ouarzazate	MA		30.92	-6.89	77603
Oudtshoorn	ZA		-33.60	22.20	73694
Oued Lill	TN		36.83	10.04	66100
Oued Rhiou	DZ		35.96	0.92	55430
Oued Zem	MA		32.86	-6.57	104029
Ouezzane	MA		34.80	-5.58	65088
Ouislane	MA		33.91	-5.49	95995
Oujda	MA		34.68	-1.91	539711
Oulad Teïma	MA		30.39	-9.21	97608
Ouled Djellal	DZ		34.43	5.06	58481
Oulu	FI		65.01	25.47	216066
Oum el Bouaghi	DZ		35.88	7.11	67201
Oumé	CI		6.38	-5.42	58606
Ourense	ES		42.34	-7.86	105233
Ouricuri	BR		-7.88	-40.08	65245
Ourinhos	BR		-22.98	-49.87	103970
Ouro Preto	BR		-20.39	-43.51	74821
Outremont	CA		45.52	-73.61	23954
Ovalle	CL		-30.60	-71.20	77138
Overbrook	US	Pennsylvania	39.99	-75.24	32181
Overland	US	Missouri	38.70	-90.36	15959
Overland Park	US	Kansas	38.98	-94.67	186515
Oviedo	ES		43.36	-5.84	220027
Oviedo	US	Florida	28.67	-81.21	38551
Owariasahi	JP		35.21	137.03	83144
Owasso	US	Oklahoma	36.27	-95.85	34542
Owatonna	US	Minnesota	44.08	-93.23	25725
Owen Sound	CA		44.57	-80.94	21341
Owendo	GA		0.29	9.50	95313
Owensboro	US	Kentucky	37.77	-87.11	59042
Owerri	NG		5.48	7.03	545000
Owings Mills	US	Maryland	39.42	-76.78	30622
Owo	NG		7.20	5.59	276574
Oxford	GB		51.75	-1.26	162100
Oxford	US	Mississippi	34.37	-89.52	22314
Oxford	US	Ohio	39.51	-84.75	22104
Oxford	US	Alabama	33.61	-85.83	21249
Oxford Circle	US	Pennsylvania	40.05	-75.07	48856
Oxnard	US	California	34.20	-119.18	207254
Oxon Hill	US	Maryland	38.80	-76.99	17722
Oxon Hill-Glassmanor	US	Maryland	38.80	-76.97	35355
Oyama	JP		36.30	139.80	167647
Oyan	NG		8.05	4.77	73622
Oyem	GA		1.60	11.58	72939
Oyo	NG		7.85	3.93	736072
Ozamiz City	PH		8.15	123.84	93082
Ozar	IN		20.09	73.93	51297
Ozark	US	Missouri	37.02	-93.21	19120
Ozerki	RU		60.04	30.31	95000
Ozersk	RU		55.76	60.70	81023
Ozone Park	US	New York	40.68	-73.84	53985
Ozubulu	NG		5.96	6.85	73812
Paarl	ZA		-33.73	18.98	236910
Pabbi	PK		34.01	71.79	52701
Pabianice	PL		51.66	19.35	70542
Pacajus	BR		-4.17	-38.46	70983
Pacatuba	BR		-3.98	-38.62	81524
Pace	US	Florida	30.60	-87.16	20039
Pachuca de Soto	MX		20.12	-98.73	256584
Pacific Grove	US	California	36.62	-121.92	15674
Pacific Palisades	US	California	34.05	-118.53	23121
Pacific Pines	AU		-27.94	153.31	16605
Pacifica	US	California	37.61	-122.49	39260
Paco	PH		14.59	120.99	79839
Padalarang	ID		-6.84	107.47	193114
Padang	ID		-0.95	100.35	942938
Padang Serai	MY		5.51	100.55	50757
Padangpanjang	ID		-0.46	100.41	58627
Padangsidempuan	ID		1.38	99.27	243843
Paderborn	DE		51.72	8.75	142161
Padre Hurtado	CL		-33.57	-70.81	63250
Padre Las Casas	CL		-38.76	-72.60	72892
Padua	IT		45.41	11.89	203725
Paducah	US	Kentucky	37.08	-88.60	24864
Paech’ŏn-ŭp	KP		37.99	126.30	159825
Paek'ak	KP		39.46	125.61	125924
Pagadian	PH		7.83	123.44	206483
Pagar Alam	ID		-4.03	103.25	70386
Pagbilao	PH		13.97	121.70	82132
Pago Pago	AS		-14.28	-170.70	11500
Pagoh	MY		2.15	102.77	95202
Paharpur	PK		32.11	70.97	76027
Pahrump	US	Nevada	36.21	-115.98	36441
Paignton	GB		50.44	-3.57	67520
Pailou	CN		30.80	108.39	104351
Paine	CL		-33.81	-70.74	72759
Painesville	US	Ohio	41.72	-81.25	19776
Paisley	GB		55.83	-4.43	77270
Paita	PE		-5.09	-81.11	56151
Pak Kret	TH		13.91	100.50	190272
Pakenham	AU		-38.07	145.47	54118
Pakokku	MM		21.33	95.08	126938
Pakpattan	PK		30.34	73.39	126706
Pakse	LA		15.12	105.80	77900
Pala	TD		9.36	14.91	70677
Palaió Fáliro	GR		37.93	23.70	64021
Palakkad	IN		10.77	76.65	132728
Palakollu	IN		16.52	81.73	81199
Palangkaraya	ID		-2.21	113.92	318247
Palani	IN		10.45	77.52	70467
Palapye	BW		-22.55	27.13	52636
Palatine	US	Illinois	42.11	-88.03	69308
Palembang	ID		-2.92	104.75	1801367
Palencia	ES		42.01	-4.52	78629
Palermo	IT		38.12	13.36	648260
Palestine	US	Texas	31.76	-95.63	18288
Palhoça	BR		-27.65	-48.67	175272
Palikir	FM		6.92	158.16	6942
Palimanan	ID		-6.71	108.42	92600
Palisades Park	US	New Jersey	40.85	-74.00	20743
Pallabi	BD		23.82	90.37	597574
Pallichal	IN		8.45	77.03	53861
Pallāvaram	IN		12.97	80.15	233984
Palm Bay	US	Florida	28.03	-80.59	119760
Palm Beach	AU		-28.12	153.47	15205
Palm Beach Gardens	US	Florida	26.82	-80.14	52923
Palm City	US	Florida	27.17	-80.27	23120
Palm Coast	US	Florida	29.58	-81.21	82893
Palm Desert	US	California	33.72	-116.38	51869
Palm Harbor	US	Florida	28.08	-82.76	57439
Palm River-Clair Mel	US	Florida	27.92	-82.38	21024
Palm Springs	US	California	33.83	-116.55	47371
Palm Springs	US	Florida	26.64	-80.10	22341
Palm Valley	US	Florida	30.18	-81.39	20019
Palma	ES		39.57	2.65	438234
Palma Soriano	CU		20.21	-75.99	102826
Palmaner	IN		13.20	78.75	54035
Palmares	BR		-8.68	-35.59	54584
Palmas	BR		-10.17	-48.33	306296
Palmdale	US	California	34.58	-118.12	158351
Palmer	US	Massachusetts	42.16	-72.33	18261
Palmers Green	GB		51.62	-0.11	15162
Palmerston	AU		-12.49	130.98	33695
Palmerston North	NZ		-40.36	175.61	90500
Palmetto Bay	US	Florida	25.62	-80.32	24439
Palmira	CO		3.54	-76.30	312519
Palo Alto	US	California	37.44	-122.14	66853
Palo Negro	VE		10.17	-67.54	128875
Palopo	ID		-2.99	120.20	184961
Palos Hills	US	Illinois	41.70	-87.82	17565
Paltan	BD		23.74	90.41	184492
Palu	ID		-0.91	119.87	389959
Palwal	IN		28.14	77.33	131926
Palwancha	IN		17.58	80.68	80199
Palín	GT		14.40	-90.70	65873
Palāsa	IN		18.77	84.41	65833
Pamanukan	ID		-6.28	107.81	114290
Pamekasan	ID		-7.16	113.47	92447
Pammal	IN		12.97	80.13	75870
Pampa	US	Texas	35.54	-100.96	18177
Pampatar	VE		11.00	-63.79	64983
Pamplona	ES		42.82	-1.64	208243
Pamplona	CO		7.38	-72.65	53587
Pampán	VE		9.45	-70.48	59657
Pamulang	ID		-6.34	106.74	174557
Panabo	PH		7.31	125.68	211242
Panalanoy	PH		11.25	125.01	189090
Panama City	PA		8.99	-79.52	408168
Panama City	US	Florida	30.16	-85.66	38286
Panchkula	IN		30.69	76.85	211355
Pandak	ID		-7.91	110.29	56043
Pandamaran	MY		3.01	101.42	53916
Pandeglang	ID		-6.31	106.11	92316
Pandharpur	IN		17.68	75.33	98923
Pandi	PH		14.87	120.96	162725
Pandit Deen Dayal Upadhyaya Nagar	IN		25.28	83.12	109650
Panevėžys	LT		55.73	24.36	85885
Pangkalanbuun	ID		-2.68	111.63	108814
Pangkalpinang	ID		-2.13	106.11	226297
Panguíla	AO		-8.69	13.45	158068
Panipat	IN		29.39	76.97	295970
Panipat Taraf Makhdum Zadgan	IN		29.42	76.99	67998
Paniqui	PH		15.67	120.58	106190
Panjim	IN		15.50	73.83	70991
Panjin	CN		41.12	122.07	1166481
Pankow	DE		52.57	13.40	65375
Panlong	CN		29.50	105.37	51177
Panna	IN		24.72	80.19	59091
Pano Aqil	PK		27.86	69.11	102701
Panorama Hills	CA		51.15	-114.08	25535
Panruti	IN		11.78	79.55	60323
Panshan	CN		41.19	122.05	625040
Panshi	CN		42.94	126.06	80200
Pantin	FR		48.89	2.41	52922
Panvel	IN		18.99	73.11	195373
Panzhihua	CN		26.59	101.71	787177
Panzos	GT		15.40	-89.64	71846
Pančevo	RS		44.87	20.64	76654
Pan’an	CN		34.75	105.11	70072
Paombong	PH		14.83	120.79	58453
Paoy Paet	KH		13.66	102.56	98934
Papakura	NZ		-37.06	174.94	37720
Papantla de Olarte	MX		20.45	-97.32	53546
Papatoetoe	NZ		-36.97	174.84	56010
Papeete	PF		-17.53	-149.57	26357
Papillion	US	Nebraska	41.15	-96.04	19510
Paracatu	BR		-17.22	-46.87	94023
Paradise	US	Nevada	36.10	-115.15	223167
Paradise	US	California	39.76	-121.62	26476
Paradise	CA		47.53	-52.88	22957
Parafield Gardens	AU		-34.78	138.61	16872
Paragominas	BR		-3.00	-47.35	105550
Paragould	US	Arkansas	36.06	-90.50	27900
Paraiso	MX		18.40	-93.21	86632
Parakou	BJ		9.34	2.63	255478
Paralakhemundi	IN		18.78	84.10	87152
Paralowie	AU		-34.76	138.61	16530
Paramagudi	IN		9.55	78.59	95579
Paramaribo	SR		5.87	-55.17	223757
Paramount	US	California	33.89	-118.16	55412
Paramus	US	New Jersey	40.94	-74.08	26974
Paranaguá	BR		-25.52	-48.53	141013
Paranaque City	PH		14.48	121.02	703245
Paranavaí	BR		-23.07	-52.47	92001
Parand	IR		35.47	50.98	97464
Paranoá	BR		-15.78	-47.78	63923
Paraná	AR		-31.73	-60.53	247139
Paraparaumu	NZ		-40.92	175.02	29900
Parauapebas	BR		-6.07	-49.90	267836
Paraíso do Tocantins	BR		-10.18	-48.87	55164
Parbhani	IN		19.27	76.77	307170
Parc-Extension	CA		45.53	-73.63	33800
Pardubice	CZ		50.04	15.78	88520
Pardīs	IR		35.75	51.81	114249
Pare	ID		-7.77	112.20	106007
Parelheiros	BR		-23.83	-46.73	153695
Parepare	ID		-4.01	119.63	160309
Pariaman	ID		-0.62	100.12	92183
Parintins	BR		-2.63	-56.74	101956
Paris	FR		48.85	2.35	2138551
Paris	US	Texas	33.66	-95.56	24782
Paris 05 Panthéon	FR		48.84	2.35	55252
Paris 09 Opéra	FR		48.87	2.34	57271
Paris 10 Entrepôt	FR		48.87	2.36	83873
Paris 10e Arrondissement	FR		48.88	2.36	83459
Paris 11 Popincourt	FR		48.86	2.38	138170
Paris 11e Arrondissement	FR		48.86	2.38	144292
Paris 12 Reuilly	FR		48.84	2.39	138024
Paris 12e Arrondissement	FR		48.84	2.44	140311
Paris 13 Gobelins	FR		48.83	2.36	181271
Paris 13e Arrondissement	FR		48.83	2.36	177833
Paris 14 Observatoire	FR		48.83	2.33	136455
Paris 15 Vaugirard	FR		48.84	2.30	229713
Paris 16 Passy	FR		48.86	2.28	159386
Paris 17 Batignolles-Monceau	FR		48.88	2.32	159212
Paris 18 Buttes-Montmartre	FR		48.89	2.34	183127
Paris 19 Buttes-Chaumont	FR		48.88	2.38	178691
Paris 20 Ménilmontant	FR		48.86	2.40	185140
Parit	MY		4.48	100.92	60988
Parit Sulung	MY		1.98	102.88	82399
Park Forest	US	Illinois	41.49	-87.67	21954
Park Ridge	US	Illinois	42.01	-87.84	37757
Park Slope	US	New York	40.67	-73.99	65047
Park View	US	District of Columbia	38.93	-77.02	18796
Parkchester	US	New York	40.84	-73.86	65876
Parkent	UZ		41.29	69.68	60200
Parker	US	Colorado	39.52	-104.76	49550
Parkersburg	US	West Virginia	39.27	-81.56	30991
Parkland	US	Washington	47.16	-122.43	35803
Parkland	US	Florida	26.31	-80.24	30177
Parkside	US	California	37.74	-122.49	16874
Parkville	US	Maryland	39.38	-76.54	30734
Parkwood Manor	US	Pennsylvania	40.09	-74.97	16787
Parkwoods-Donalda	CA		43.76	-79.33	34805
Parla	ES		40.24	-3.77	115611
Parli Vaijnāth	IN		18.85	76.53	94863
Parlier	US	California	36.61	-119.53	15138
Parma	IT		44.80	10.33	198292
Parma	US	Ohio	41.40	-81.72	79937
Parma Heights	US	Ohio	41.39	-81.76	20246
Parnamirim	BR		-5.92	-35.26	271713
Parnas	RU		60.07	30.35	66693
Parnaíba	BR		-2.90	-41.78	138008
Parobé	BR		-29.63	-50.83	52058
Parole	US	Maryland	38.98	-76.55	15922
Parque Do Carmo	BR		-23.58	-46.46	74677
Parramatta	AU		-33.82	151.00	30211
Parsippany	US	New Jersey	40.86	-74.43	51144
Parung	ID		-6.42	106.73	128905
Parys	ZA		-26.90	27.46	71319
Pará de Minas	BR		-19.86	-44.61	97139
Parādīp Garh	IN		20.32	86.61	85868
Pasadena	US	Texas	29.69	-95.21	153784
Pasadena	US	California	34.15	-118.14	142250
Pasadena	US	Maryland	39.12	-76.57	24287
Pasarkemis	ID		-6.17	106.53	263289
Pasay	PH		14.54	121.00	416522
Pascagoula	US	Mississippi	30.37	-88.56	22126
Pasco	US	Washington	46.24	-119.10	69451
Pascoe Vale	AU		-37.73	144.93	18171
Paseh	ID		-7.07	107.79	126181
Pasig City	PH		14.59	121.06	853050
Pasir Gudang	MY		1.46	103.91	534659
Pasir Mas	MY		6.05	102.14	230424
Pasir Puteh	MY		5.83	102.40	137400
Pasir Ris New Town	SG		1.37	103.95	54420
Paso Robles	US	California	35.63	-120.69	27157
Pasrur	PK		32.26	74.66	102717
Passaic	US	New Jersey	40.86	-74.13	71085
Passau	DE		48.57	13.43	50560
Passo Fundo	BR		-28.26	-52.41	179529
Passos	BR		-20.72	-46.61	111939
Pasto	CO		1.21	-77.28	392930
Pasuruan	ID		-7.65	112.91	213469
Pataskala	US	Ohio	40.00	-82.67	15245
Paterna	ES		39.50	-0.44	64023
Pateros	PH		14.54	121.07	63840
Paterson	US	New Jersey	40.92	-74.17	147754
Pathein	MM		16.78	94.73	237089
Pathum Wan	TH		13.74	100.52	53263
Pathānkot	IN		32.27	75.65	174306
Pati	ID		-6.76	111.04	107028
Patiya	BD		22.30	91.98	51360
Patiāla	IN		30.34	76.39	446246
Patna	IN		25.59	85.14	1684297
Patnos	TR		39.22	42.86	87451
Pato Branco	BR		-26.23	-52.67	91836
Patos	BR		-7.02	-37.28	92575
Patos de Minas	BR		-18.58	-46.52	159235
Patrocínio	BR		-18.94	-46.99	89826
Pattaya	TH		12.93	100.88	116417
Patterson	US	California	37.47	-121.13	21498
Pattoki	PK		31.02	73.85	113735
Pattukkottai	IN		10.42	79.32	73135
Patuakhali	BD		22.37	90.35	65000
Patuto	PH		14.12	120.97	52883
Patzún	GT		14.68	-91.01	58240
Pau	FR		43.31	-0.36	82697
Paudalho	BR		-7.90	-35.18	56665
Paulista	BR		-7.94	-34.87	342167
Paulo Afonso	BR		-9.41	-38.21	112870
Paulínia	BR		-22.76	-47.15	110537
Pavia	IT		45.19	9.16	65734
Pavlodar	KZ		52.28	76.97	329002
Pavlohrad	UA		48.53	35.87	101430
Pavlovo	RU		55.97	43.09	63338
Pavlovskiy Posad	RU		55.78	38.65	60051
Pawtucket	US	Rhode Island	41.88	-71.38	71591
Paya Terubong	MY		5.37	100.28	226712
Payakumbuh	ID		-0.22	100.63	139576
Paysandú	UY		-32.32	-58.08	81550
Payson	US	Utah	40.04	-111.73	19548
Payson	US	Arizona	34.23	-111.33	15345
Payyanur	IN		12.09	75.20	72111
Pazardzhik	BG		42.20	24.33	55220
Paço do Lumiar	BR		-2.53	-44.11	145643
Peabody	US	Massachusetts	42.53	-70.93	52504
Peacehaven	GB		50.79	-0.01	18579
Peachtree City	US	Georgia	33.40	-84.60	35240
Peachtree Corners	US	Georgia	33.97	-84.22	40978
Pearl	US	Mississippi	32.27	-90.13	26462
Pearl City	US	Hawaii	21.40	-157.98	47698
Pearl River	US	New York	41.06	-74.02	15876
Pearland	US	Texas	29.56	-95.29	108821
Pecan Grove	US	Texas	29.63	-95.73	15963
Pecangaan	ID		-6.70	110.71	61046
Pechersk	UA		50.44	30.52	100900
Peckham	GB		51.47	-0.07	71552
Pedregal	PA		9.07	-79.43	51641
Pedreira	BR		-23.71	-46.65	163586
Pedro Juan Caballero	PY		-22.55	-55.74	75109
Pedro Leopoldo	BR		-19.62	-44.04	62580
Peekskill	US	New York	41.29	-73.92	24043
Peicheng	CN		34.74	116.92	195363
Pekalongan	ID		-6.89	109.68	324564
Pekanbaru	ID		0.52	101.44	1167599
Pekin	US	Illinois	40.57	-89.64	33223
Pelabuhanratu	ID		-6.99	106.55	109523
Pelentong	MY		1.52	103.82	583640
Pelham	US	Alabama	33.29	-86.81	22885
Pelotas	BR		-31.77	-52.34	320674
Pemalang	ID		-6.89	109.38	184149
Pemangkat	ID		1.17	108.97	54259
Pematangsiantar	ID		2.96	99.07	279198
Pemba	MZ		-12.97	40.52	232932
Pembroke Pines	US	Florida	26.00	-80.22	166611
Penarth	GB		51.44	-3.17	23437
Pendang	MY		6.00	100.48	94033
Pendleton	US	Oregon	45.67	-118.79	16881
Penedo	BR		-10.29	-36.59	60189
Pengcheng	CN		36.43	114.17	68442
Pengpu	CN		31.29	121.44	152725
Pengze	CN		29.90	116.55	350000
Penicuik	GB		55.83	-3.23	16150
Penn Hills	US	Pennsylvania	40.50	-79.84	44610
Pennsauken	US	New Jersey	39.96	-75.06	36332
Pennsport	US	Pennsylvania	39.93	-75.15	26000
Penrith	GB		54.67	-2.76	16700
Pensacola	US	Florida	30.42	-87.22	53724
Penticton	CA		49.48	-119.59	33761
Penza	RU		53.20	45.01	523553
Penzance	GB		50.12	-5.54	19872
Penzing	AT		48.20	16.27	98176
Penápolis	BR		-21.42	-50.08	61679
Peoria	US	Arizona	33.58	-112.24	190985
Peoria	US	Illinois	40.69	-89.59	115070
Perai	MY		5.38	100.38	65301
Peranāmpattu	IN		12.93	78.72	51271
Perbaungan	ID		3.57	98.96	157174
Percut	ID		3.63	98.86	311063
Perdizes	BR		-23.54	-46.68	102391
Pereira	CO		4.81	-75.69	467269
Pergamino	AR		-33.89	-60.57	91399
Peristéri	GR		38.02	23.69	139981
Periya Semūr	IN		11.36	77.69	55282
Perling	MY		1.48	103.68	101263
Perm	RU		58.01	56.25	982419
Pernik	BG		42.60	23.03	82467
Perpignan	FR		42.70	2.90	110706
Perris	US	California	33.78	-117.23	74971
Perry	US	Georgia	32.46	-83.73	15457
Perry Hall	US	Maryland	39.41	-76.46	28474
Perry Vale	GB		51.44	-0.04	15618
Perrysburg	US	Ohio	41.56	-83.63	21423
Perth	AU		-31.95	115.86	2384371
Perth	GB		56.40	-3.43	47350
Perth Amboy	US	New Jersey	40.51	-74.27	52682
Perugia	IT		43.11	12.39	120137
Perus	BR		-23.40	-46.75	87823
Peruíbe	BR		-24.32	-47.00	68352
Pervomaysk	UA		48.04	30.85	62426
Pervouralsk	RU		56.91	59.94	133600
Pesaro	IT		43.91	12.92	77241
Pescara	IT		42.46	14.20	119554
Peshawar	PK		34.01	71.58	4758762
Pesqueira	BR		-8.36	-36.70	62722
Pessac	FR		44.81	-0.63	57944
Pest	HU		47.50	19.08	1001748
Pestlőrinc	HU		47.43	19.22	58722
Petaẖ Tiqva	IL		32.09	34.89	253529
Petaling Jaya	MY		3.11	101.61	807879
Petaluma	US	California	38.23	-122.64	60438
Petapa	GT		14.50	-90.56	135447
Petare	VE		10.48	-66.81	364684
Petauke	ZM		-14.24	31.32	58156
Petawawa	CA		45.89	-77.28	17187
Peterborough	GB		52.57	-0.25	163379
Peterborough	CA		44.30	-78.32	85807
Peterhead	GB		57.51	-1.78	19060
Peterhof	RU		59.88	29.90	73199
Peterlee	GB		54.76	-1.34	20300
Petersburg	US	Virginia	37.23	-77.40	32477
Petlād	IN		22.48	72.80	55330
Petrodvorets	RU		59.90	29.80	61973
Petrogradka	RU		59.97	30.31	130455
Petrolina	BR		-9.40	-40.50	386791
Petropavl	KZ		54.87	69.15	200920
Petropavlovsk-Kamchatsky	RU		53.06	158.63	181216
Petrozavodsk	RU		61.78	34.35	279190
Petroúpolis	GR		38.04	23.68	58979
Petrópolis	BR		-22.50	-43.18	272691
Petržalka	SK		48.12	17.13	112380
Petworth	US	District of Columbia	38.95	-77.02	18983
Peñaflor	CL		-33.61	-70.88	85671
Peñalolén	CL		-33.47	-70.53	241599
Pflugerville	US	Texas	30.44	-97.62	57122
Pforzheim	DE		48.88	8.70	119313
Phagwāra	IN		31.22	75.77	100146
Phalaborwa	ZA		-23.94	31.14	109468
Phalia	PK		32.43	73.58	62453
Phaltan	IN		17.99	74.43	53202
Phan Rang-Tháp Chàm	VN		11.56	108.99	207998
Phan Thiết	VN		10.93	108.10	228536
Pharr	US	Texas	26.19	-98.18	76538
Phasi Charoen	TH		13.71	100.44	122070
Phaya Thai	TH		13.78	100.54	70238
Phenix City	US	Alabama	32.47	-85.00	37570
Phetchabun	TH		16.42	101.16	50656
Philadelphia	US	Pennsylvania	39.95	-75.16	1573916
Philipsburg	SX		18.03	-63.05	1400
Phitsanulok	TH		16.82	100.26	62584
Phnom Penh	KH		11.56	104.92	1573544
Phoenix	US	Arizona	33.45	-112.07	1650070
Phoenixville	US	Pennsylvania	40.13	-75.51	16658
Phong Thạnh	VN		9.32	105.35	53912
Phong Điền	VN		16.58	107.36	114820
Phong Điền	VN		10.00	105.67	98424
Phool Nagar	PK		31.20	73.95	114530
Phra Khanong	TH		13.70	100.60	90354
Phra Nakhon	TH		13.77	100.50	51231
Phra Nakhon Si Ayutthaya	TH		14.35	100.58	50830
Phra Phutthabat	TH		14.73	100.80	57008
Phra Pradaeng	TH		13.66	100.53	196129
Phu Quoc	VN		10.22	103.97	294419
Phuket	TH		7.89	98.40	79308
Phulwari Sharif	IN		25.58	85.07	81740
Phusro	IN		23.76	86.01	185555
Phuthaditjhaba	ZA		-28.52	28.82	84258
Phú Mỹ	VN		10.63	107.07	287055
Phú Quốc	VN		10.29	104.01	179480
Phú Thọ	VN		21.40	105.22	91650
Phúc Yên	VN		21.24	105.70	180000
Phổ Yên	VN		21.42	105.89	231363
Phủ Lý	VN		20.55	105.91	136654
Piacenza	IT		45.05	9.69	103607
Pianura	IT		40.86	14.17	57821
Piatra Neamţ	RO		46.92	26.33	102688
Picheng	CN		34.47	117.97	64585
Pickering	CA		43.90	-79.13	91771
Pickerington	US	Ohio	39.88	-82.75	19745
Picnic Point-North Lynnwood	US	Washington	47.86	-122.29	22953
Pico Rivera	US	California	33.98	-118.10	64218
Picos	BR		-7.08	-41.47	83090
Picpus	FR		48.84	2.40	61920
Pidugurālla	IN		16.48	79.89	63103
Piedade	BR		-23.71	-47.43	52970
Piedecuesta	CO		6.99	-73.05	163362
Piedras Negras	MX		28.70	-100.52	150178
Piekary Śląskie	PL		50.38	18.93	59757
Pierrefonds	CA		45.46	-73.89	59093
Pierrefonds-Roxboro	CA		45.50	-73.84	73194
Piet Retief	ZA		-27.01	30.81	84349
Pietermaritzburg	ZA		-29.62	30.39	839327
Pijijiapan	MX		15.69	-93.21	50079
Pikesville	US	Maryland	39.37	-76.72	30764
Pikine	SN		14.76	-17.39	1170791
Pilar	AR		-34.46	-58.91	81120
Pilkhua	IN		28.71	77.66	74212
Pilsen	CZ		49.75	13.38	168733
Pimlico	GB		51.49	-0.14	20709
Pimpri	IN		18.62	73.81	1284606
Pimpri-Chinchwad	IN		18.62	73.80	1727692
Pinar del Rey	ES		40.47	-3.65	52031
Pinar del Río	CU		22.42	-83.70	186990
Pindamonhangaba	BR		-22.92	-45.46	165428
Pindi Bhattian	PK		31.90	73.27	493222
Pindi Gheb	PK		33.24	72.26	63810
Pindiga	NG		9.98	10.95	106322
Pine Bluff	US	Arkansas	34.23	-92.00	44772
Pine Hills	US	Florida	28.56	-81.45	60076
Pinecrest	US	Florida	25.67	-80.31	19452
Pinehurst	US	North Carolina	35.20	-79.47	15752
Pinellas Park	US	Florida	27.84	-82.70	51617
Pinetown	ZA		-29.82	30.89	144026
Pinewood	US	Florida	25.87	-80.22	16520
Pingdingshan	CN		33.73	113.32	979130
Pingdu	CN		36.78	119.95	542234
Pingjin	CN		30.61	107.54	55139
Pingliang	CN		35.54	106.69	504848
Pingnan	CN		23.54	110.39	62483
Pingshan	CN		22.99	114.71	113631
Pingwu County	CN		32.41	104.53	180000
Pingxiang	CN		27.62	113.85	893550
Pingxiang	CN		22.10	106.76	129843
Pingyi	CN		35.50	117.63	78254
Pingyin	CN		36.28	116.45	62050
Pingzhuang	CN		42.04	119.29	67273
Pinhais	BR		-25.44	-49.19	117000
Pinheiro	BR		-2.52	-45.08	84621
Pinheiros	BR		-23.57	-46.69	65145
Pinner	GB		51.59	-0.38	19158
Pinole	US	California	38.00	-122.30	19269
Pinsk	BY		52.12	26.07	123283
Piotrków Trybunalski	PL		51.41	19.70	80128
Piqua	US	Ohio	40.14	-84.24	20790
Pir Jo Goth	PK		27.59	68.62	54266
Pir Mahal	PK		30.77	72.43	52476
Piracicaba	BR		-22.73	-47.65	407252
Piraeus	GR		37.94	23.65	163688
Piranshahr	IR		36.70	45.14	168393
Pirapora	BR		-17.34	-44.94	55606
Piraquara	BR		-25.44	-49.07	118730
Pirassununga	BR		-22.00	-47.43	73545
Piripiri	BR		-4.27	-41.78	65538
Pirituba	BR		-23.49	-46.73	179724
Pirojpur	BD		22.58	89.98	54418
Pisa	IT		43.71	10.40	109960
Piscataway	US	New Jersey	40.50	-74.40	56044
Pisco	PE		-13.71	-76.21	61869
Pistoia	IT		43.93	10.92	73832
Pita Kotte	LK		6.89	79.90	118179
Pitalito	CO		1.85	-76.05	135711
Piteşti	RO		44.85	24.87	141275
Pithampur	IN		22.60	75.70	126200
Pithāpuram	IN		17.12	82.25	54859
Pitsea	GB		51.56	0.51	25000
Pitt Meadows	CA		49.22	-122.69	18573
Pittsburg	US	California	38.03	-121.88	69424
Pittsburg	US	Kansas	37.41	-94.70	20409
Pittsburgh	US	Pennsylvania	40.44	-80.00	304391
Pittsfield	US	Massachusetts	42.45	-73.25	43303
Pittwater	AU		-33.67	151.30	63482
Piura	PE		-5.18	-80.66	630000
Pivdenna Borshchahivka	UA		50.41	30.40	50500
Pizhou	CN		34.31	117.95	343421
Piła	PL		53.15	16.74	75532
Placentia	US	California	33.87	-117.87	52495
Placetas	CU		22.31	-79.65	55408
Plainfield	US	New Jersey	40.63	-74.41	51217
Plainfield	US	Illinois	41.63	-88.20	42527
Plainfield	US	Indiana	39.70	-86.40	30590
Plainfield	US	Connecticut	41.68	-71.92	15498
Plainview	US	New York	40.78	-73.47	26217
Plainview	US	Texas	34.18	-101.71	20919
Plainville	US	Connecticut	41.67	-72.86	17328
Planaltina	BR		-15.62	-47.65	189412
Planaltina	BR		-15.45	-47.61	105031
Planeta Rica	CO		8.41	-75.59	69708
Plano	US	Texas	33.02	-96.70	283558
Plano Piloto	BR		-15.79	-47.88	198697
Plant City	US	Florida	28.02	-82.11	37406
Plantation	US	Florida	26.13	-80.23	92560
Plaridel	PH		14.89	120.86	120939
Plattsburgh	US	New York	44.70	-73.45	19806
Plauen	DE		50.50	12.14	66412
Playa del Carmen	MX		20.63	-87.08	149923
Plaza de la Revolución	CU		23.12	-82.39	139135
Pleasant Grove	US	Utah	40.36	-111.74	38052
Pleasant Hill	US	California	37.95	-122.06	34810
Pleasant Plains	US	District of Columbia	38.93	-77.03	21174
Pleasant Prairie	US	Wisconsin	42.55	-87.93	20726
Pleasant View	CA		43.79	-79.34	15818
Pleasanton	US	California	37.66	-121.87	79510
Pleasantville	US	New Jersey	39.39	-74.52	20755
Pleasure Ridge Park	US	Kentucky	38.15	-85.86	25813
Pleiku	VN		13.98	108.00	114225
Pleven	BG		43.42	24.62	90209
Ploieşti	RO		44.95	26.02	180540
Plottier	AR		-38.97	-68.23	52291
Plovdiv	BG		42.15	24.75	329489
Plum	US	Pennsylvania	40.50	-79.75	27505
Plumbon	ID		-6.71	108.47	167105
Plumstead	GB		51.48	0.08	16736
Plymouth	GB		50.37	-4.14	260203
Plymouth	US	Minnesota	45.01	-93.46	75907
Plymouth	MS		16.71	-62.21	0
Plymstock	GB		50.36	-4.09	24103
Poblacion	PH		14.38	121.03	124554
Pocatello	US	Idaho	42.87	-112.45	54441
Podgorica	ME		42.44	19.26	236852
Podilskyi	UA		48.50	32.28	86652
Podolsk	RU		55.42	37.55	179400
Pohang	KR		36.03	129.36	492041
Poinciana	US	Florida	28.14	-81.46	53193
Point Breeze	US	Pennsylvania	39.93	-75.18	16977
Point Cook	AU		-37.91	144.75	66781
Point Pedro	LK		9.82	80.23	89810
Point Pleasant	US	New Jersey	40.08	-74.07	18523
Pointe-Claire	CA		45.45	-73.82	30161
Pointe-Noire	CG		-4.78	11.86	1032000
Poitiers	FR		46.58	0.34	85960
Pok Fu Lam	HK		22.27	114.13	77100
Pokhara	NP		28.27	83.97	600051
Pokrovsk	UA		48.28	37.18	60127
Pokrovskoye-Streshnëvo	RU		55.81	37.46	55000
Polanco	MX		19.43	-99.20	50000
Polangui	PH		13.29	123.49	89176
Polatlı	TR		39.58	32.14	93262
Polevskoy	RU		56.44	60.19	65770
Polewali	ID		-3.43	119.34	65800
Pollachi	IN		10.66	77.01	90180
Polokwane	ZA		-23.90	29.47	272461
Polomolok	PH		6.22	125.06	63987
Polotsk	BY		55.49	28.79	79285
Poltava	UA		49.59	34.55	279593
Pom Prap Sattru Phai	TH		13.76	100.51	51006
Pomona	US	California	34.06	-117.75	153266
Pompano Beach	US	Florida	26.24	-80.12	107762
Ponca City	US	Oklahoma	36.71	-97.09	24758
Ponce	PR		18.01	-66.62	137491
Ponders End	GB		51.64	-0.05	15664
Ponferrada	ES		42.55	-6.60	68736
Pongch’ŏn-ŭp	KP		38.12	126.20	79740
Ponnur	IN		16.07	80.55	59913
Ponnāni	IN		10.77	75.93	105512
Ponnūru	IN		16.07	80.55	57170
Ponorogo	ID		-7.87	111.46	79026
Ponta Grossa	BR		-25.09	-50.16	292177
Ponta Porã	BR		-22.54	-55.73	92017
Ponte Nova	BR		-20.42	-42.91	57776
Ponte Rasa	BR		-23.52	-46.49	89881
Ponte Vedra Beach	US	Florida	30.24	-81.39	35400
Pontefract	GB		53.69	-1.31	44710
Pontes e Lacerda	BR		-15.23	-59.34	54795
Pontevedra	ES		42.43	-8.64	82802
Pontiac	US	Michigan	42.64	-83.29	59917
Pontianak	ID		-0.03	109.33	686019
Ponticelli	IT		40.85	14.33	52284
Pontypool	GB		51.70	-3.04	35686
Pontypridd	GB		51.60	-3.34	31206
Poole	GB		50.71	-1.98	151500
Pooler	US	Georgia	32.12	-81.25	23133
Poonamalle	IN		13.05	80.11	60607
Popayán	CO		2.44	-76.61	318059
Poplar Bluff	US	Missouri	36.76	-90.39	17266
Porbandar	IN		21.64	69.61	152760
Pori	FI		61.48	21.79	83157
Porirua	NZ		-41.13	174.85	61500
Porlamar	VE		10.96	-63.87	216234
Port Alberni	CA		49.24	-124.80	20712
Port Angeles	US	Washington	48.12	-123.43	19448
Port Area	PH		14.59	120.97	72605
Port Arthur	US	Texas	29.89	-93.94	55340
Port Blair	IN		11.67	92.75	112050
Port Charlotte	US	Florida	26.98	-82.09	54392
Port Chester	US	New York	41.00	-73.67	29620
Port Colborne	CA		42.90	-79.23	18306
Port Coquitlam	CA		49.27	-122.77	58000
Port Dickson	MY		2.52	101.80	119300
Port Harcourt	NG		4.78	7.01	2120000
Port Hedland	AU		-20.31	118.61	15298
Port Hueneme	US	California	34.15	-119.20	22423
Port Huron	US	Michigan	42.97	-82.42	29330
Port Louis	MU		-20.16	57.50	155226
Port Macquarie	AU		-31.43	152.91	51965
Port Melbourne	AU		-37.84	144.94	17633
Port Moody	CA		49.28	-122.82	27512
Port Moresby	PG		-9.48	147.15	283733
Port of Spain	TT		10.67	-61.52	49031
Port Orange	US	Florida	29.14	-81.00	59866
Port Richmond	US	Pennsylvania	39.99	-75.10	27554
Port Richmond	US	New York	40.63	-74.14	15470
Port Said	EG		31.27	32.30	780515
Port Saint Lucie	US	Florida	27.29	-80.35	164603
Port Shepstone	ZA		-30.74	30.45	52793
Port Sudan	SD		19.62	37.22	489725
Port Washington	US	New York	40.83	-73.70	15846
Port-au-Prince	HT		18.54	-72.34	1234742
Port-de-Paix	HT		19.94	-72.83	306217
Port-Gentil	GA		-0.72	8.78	164018
Portadown	GB		54.42	-6.44	32926
Portage	US	Michigan	42.20	-85.58	48177
Portage	US	Indiana	41.58	-87.18	36738
Portage Park	US	Illinois	41.96	-87.77	64841
Portel	BR		-1.94	-50.82	62503
Porterville	US	California	36.07	-119.02	56058
Porthcawl	GB		51.48	-3.70	15672
Portici	IT		40.82	14.34	53801
Portishead	GB		51.48	-2.77	26355
Portland	US	Oregon	45.52	-122.68	652503
Portland	US	Maine	43.66	-70.26	66881
Portland	US	Texas	27.88	-97.32	16116
Portlaoise	IE		53.03	-7.30	23494
Portmore	JM		17.97	-76.89	102861
Porto	PT		41.15	-8.61	252687
Porto Alegre	BR		-30.03	-51.23	1488252
Porto Amboim	AO		-10.73	13.77	91605
Porto Feliz	BR		-23.21	-47.52	53402
Porto Ferreira	BR		-21.85	-47.48	52649
Porto Nacional	BR		-10.71	-48.42	68555
Porto Seguro	BR		-16.45	-39.06	168326
Porto Velho	BR		-8.76	-63.90	548952
Porto-Novo	BJ		6.50	2.60	264320
Portoviejo	EC		-1.06	-80.45	321800
Portslade	GB		50.84	-0.22	20000
Portsmouth	GB		50.80	-1.09	208100
Portsmouth	US	Virginia	36.84	-76.30	96201
Portsmouth	US	New Hampshire	43.08	-70.76	21530
Portsmouth	US	Ohio	38.73	-83.00	20409
Portsmouth	US	Rhode Island	41.60	-71.25	17756
Portsmouth Heights	US	Virginia	36.82	-76.37	99049
Porvoo	FI		60.39	25.67	51853
Porz am Rhein	DE		50.89	7.06	113415
Posadas	AR		-27.39	-55.92	305874
Post Falls	US	Idaho	47.72	-116.95	30453
Potchefstroom	ZA		-26.72	27.10	178285
Potenza	IT		40.64	15.81	56433
Potiskum	NG		11.71	11.08	86002
Potomac	US	Maryland	39.02	-77.21	44965
Potosí	BO		-19.58	-65.75	141251
Potsdam	DE		52.40	13.07	184754
Potters Bar	GB		51.69	-0.18	22639
Pottstown	US	Pennsylvania	40.25	-75.65	22664
Poughkeepsie	US	New York	41.70	-73.92	30371
Poulton-le-Fylde	GB		53.83	-2.98	19914
Pouso Alegre	BR		-22.23	-45.94	152217
Pouytenga	BF		12.25	-0.43	96469
Poway	US	California	32.96	-117.04	50157
Poyang	CN		28.99	116.67	70787
Poza Rica de Hidalgo	MX		20.53	-97.46	185242
Poznań	PL		52.41	16.93	536151
Pozniaky	UA		50.40	30.62	104400
Pozuelo de Alarcón	ES		40.43	-3.81	82428
Pozzo Strada	IT		45.07	7.63	54766
Pozzuoli	IT		40.84	14.10	81231
Poá	BR		-23.53	-46.34	103765
Poços de Caldas	BR		-21.79	-46.56	168641
Prabumulih	ID		-3.43	104.23	103470
Prachantakham	TH		14.06	101.52	59696
Praga Południe	PL		52.24	21.09	179836
Praga Północ	PL		52.25	21.03	93192
Prague	CZ		50.09	14.42	1165581
Praia	CV		14.93	-23.51	137868
Praia Grande	BR		-24.01	-46.40	349935
Prairie Village	US	Kansas	38.99	-94.63	21877
Prairieville	US	Louisiana	30.30	-90.97	26895
Prato	IT		43.88	11.10	195089
Prattville	US	Alabama	32.46	-86.46	35420
Pravyi Bereh	UA		47.11	37.59	352088
Prayagraj	IN		25.44	81.84	1073438
Preaek Prasab	KH		12.35	106.04	64466
Prenzlauer Berg	DE		52.54	13.42	148878
Prescot	GB		53.43	-2.80	40889
Prescott	US	Arizona	34.54	-112.47	41899
Prescott Valley	US	Arizona	34.61	-112.32	42197
Presidencia Roque Sáenz Peña	AR		-26.79	-60.44	81879
Presidente Franco	PY		-25.56	-54.61	54292
Presidente Prudente	BR		-22.13	-51.39	225668
Presnenskiy	RU		55.76	37.56	122000
Prestatyn	GB		53.34	-3.41	19085
Preston	GB		53.76	-2.70	313332
Preston	AU		-37.75	145.02	33790
Prestons	AU		-33.94	150.87	15312
Prestwich	GB		53.53	-2.28	31500
Pretoria	ZA		-25.74	28.19	2112693
Prešov	SK		49.00	21.24	82927
Prichard	US	Alabama	30.74	-88.08	22351
Prilep	MK		41.35	21.55	73814
Primrose Place	GB		52.56	-0.11	17161
Prince Albert	CA		53.20	-105.77	35102
Prince Edward	CA		44.00	-77.25	25496
Prince George	CA		53.92	-122.75	78943
Princeton	US	Florida	25.54	-80.41	39308
Princeton	US	New Jersey	40.35	-74.66	29603
Prior Lake	US	Minnesota	44.71	-93.42	25282
Pristina	XK		42.67	21.17	550000
Prizren	XK		42.21	20.74	171464
Probolinggo	ID		-7.75	113.22	243746
Proddatūr	IN		14.75	78.55	177797
Prokhladnyy	RU		43.76	44.03	60800
Prokop’yevsk	RU		53.92	86.72	219000
Prospect Heights	US	Illinois	42.10	-87.94	16386
Prosper	US	Texas	33.24	-96.80	15967
Prosperidad	PH		8.58	125.90	90162
Providence	US	Rhode Island	41.82	-71.41	190934
Provo	US	Utah	40.23	-111.66	115162
Prunedale	US	California	36.78	-121.67	17560
Pruszków	PL		52.17	20.81	55371
Pryluky	UA		50.60	32.38	52553
Prymorskyi	UA		47.07	37.50	71008
Przemyśl	PL		49.78	22.77	67013
Psie Pole	PL		51.15	17.04	95615
Pskov	RU		57.82	28.33	210501
Pu'er	CN		22.79	100.97	296565
Pubal	KR		37.29	127.51	63026
Pucallpa	PE		-8.38	-74.55	326040
Pucheng	CN		27.92	118.53	59832
Puchong	MY		3.00	101.62	375181
Pudong	CN		31.24	121.50	5681512
Pudsey	GB		53.80	-1.66	25393
Puducherry	IN		11.93	79.83	657209
Pudukkottai	IN		10.38	78.82	117630
Puebla	MX		19.05	-98.21	1692181
Pueblo	US	Colorado	38.25	-104.61	109412
Pueblo Nuevo	ES		40.43	-3.64	62840
Pueblo West	US	Colorado	38.35	-104.72	29637
Puente Alto	CL		-33.61	-70.58	568106
Puente de Vallecas	ES		40.39	-3.66	244151
Puerto Ayacucho	VE		5.66	-67.58	125840
Puerto Barrios	GT		15.73	-88.60	100593
Puerto Berrío	CO		6.49	-74.40	51079
Puerto Cabello	VE		10.47	-68.01	174000
Puerto Cortez	HN		15.83	-87.93	142311
Puerto La Cruz	VE		10.21	-64.63	370000
Puerto Madryn	AR		-42.77	-65.04	64555
Puerto Maldonado	PE		-12.59	-69.20	85024
Puerto Montt	CL		-41.47	-72.94	245902
Puerto Padre	CU		21.20	-76.60	76838
Puerto Peñasco	MX		31.32	-113.54	62689
Puerto Plata	DO		19.79	-70.69	146000
Puerto Princesa	PH		9.74	118.74	222673
Puerto Vallarta	MX		20.62	-105.23	224166
Puertollano	ES		38.69	-4.11	51842
Puji	CN		36.13	119.72	52563
Pukekohe East	NZ		-37.20	174.95	21438
Pul Pehlad	IN		28.50	77.29	69657
Pul-e Khumrī	AF		35.94	68.72	56369
Pula	HR		44.87	13.85	52220
Pulandian	CN		39.40	121.97	104277
Pulheim	DE		51.00	6.81	53762
Puli	TW		23.97	120.97	86406
Pulilan	PH		14.90	120.85	111384
Pulivendla	IN		14.42	78.23	65706
Puliyankudi	IN		9.17	77.40	66034
Pullman	US	Washington	46.73	-117.18	32816
Pulong Santa Cruz	PH		14.27	121.08	126844
Punchbowl	AU		-33.93	151.05	20174
Pune	IN		18.52	73.86	3124458
Punganūru	IN		13.37	78.57	54746
Punggol	SG		1.41	103.91	204150
Puning	CN		23.31	116.17	874954
Puno	PE		-15.84	-70.02	128637
Punta Alta	AR		-38.88	-62.08	64244
Punta Arenas	CL		-53.16	-70.91	117430
Punta Cana	DO		18.58	-68.40	100023
Punta Cardón	VE		11.66	-70.22	113999
Punta de Mata	VE		9.69	-63.61	61080
Punta Gorda	US	Florida	26.93	-82.05	18150
Punta Gorda Isles	US	Florida	26.92	-82.08	18306
Punto Fijo	VE		11.69	-70.20	141729
Punāsa	IN		22.24	76.39	350000
Puqi	CN		29.72	113.88	132891
Purbalingga	ID		-7.39	109.36	56903
Puri	IN		19.80	85.82	200564
Purley	GB		51.34	-0.11	72000
Purmerend	NL		52.51	4.96	80117
Purnia	IN		25.78	87.47	282248
Pursat	KH		12.54	103.92	52476
Puruliya	IN		23.33	86.36	122533
Purwakarta	ID		-6.56	107.44	179233
Purwodadi	ID		-7.09	110.92	139387
Purwokerto	ID		-7.42	109.23	230235
Pusad	IN		19.91	77.58	73046
Pushkin	RU		59.71	30.40	92889
Pushkino	RU		55.99	37.83	102816
Putatan	PH		14.40	121.05	102146
Putatan	MY		5.93	116.06	78340
Puthia	BD		24.37	88.83	159406
Putian	CN		25.44	119.01	1539389
Putney	GB		51.46	-0.22	77140
Putra Heights	MY		2.99	101.57	60000
Putrajaya	MY		2.94	101.69	50000
Puttūr	IN		13.44	79.55	54092
Puttūr	IN		12.76	75.20	53331
Putuo	CN		31.25	121.39	1239100
Puxi	CN		31.24	121.47	6683712
Puyallup	US	Washington	47.19	-122.29	39659
Puyang	CN		29.46	119.89	3590000
Puyang	CN		35.76	115.04	655674
Puyang Chengguanzhen	CN		35.71	115.03	104994
Pyatigorsk	RU		44.05	43.05	142865
Pyay	MM		18.82	95.22	135308
Pyeongtaek	KR		36.99	127.09	364694
Pyin Oo Lwin	MM		22.04	96.46	117303
Pyinmana	MM		19.74	96.21	97409
Pyongyang	KP		39.03	125.75	3222000
Pánlóngchéng Jīngjì Kāifāqū	CN		30.69	114.27	59207
Pátra	GR		38.25	21.74	168034
Pátzcuaro	MX		19.51	-101.61	55298
Pèlèngana	ML		13.43	-6.22	50552
Pécs	HU		46.08	18.23	145347
Pétionville	HT		18.51	-72.29	376834
Pôr do Sol	BR		-15.86	-48.12	101866
Põhja-Tallinn	EE		59.45	24.70	63240
Pābna	BD		24.01	89.24	186781
Pāchora	IN		20.67	75.35	59609
Pākdasht	IR		35.48	51.68	236319
Pālang	BD		23.22	90.35	67652
Pālanpur	IN		24.17	72.44	141592
Pālghar	IN		19.70	72.77	72335
Pāli	IN		25.77	73.32	230075
Pālitāna	IN		21.53	71.82	64497
Pāloncha	IN		17.60	80.71	75224
Pānihāti	IN		22.69	88.37	378705
Pār Naogaon	BD		24.80	88.95	192464
Pārsābād	IR		39.65	47.92	102996
Pārvatipuram	IN		18.78	83.43	53844
Pātan	NP		27.68	85.31	299283
Pātan	IN		23.85	72.13	133737
Pīlibhīt	IN		28.63	79.80	131008
Pīshvā	IR		35.31	51.73	53856
Płock	PL		52.55	19.71	127474
Pūth Kalān	IN		28.71	77.08	96002
P’yŏngsŏng	KP		39.25	125.87	100000
Qabula	PK		30.18	73.07	52495
Qadirpur Ran	PK		30.29	71.67	200000
Qalyub	EG		30.18	31.21	156363
Qal‘at Bīshah	SA		20.00	42.61	81828
Qal‘at Sukkar	IQ		31.86	46.07	110000
Qamdo	CN		31.13	97.18	86280
Qaraqash	CN		37.27	79.73	66541
Qarasu	CN		44.20	80.42	71446
Qaraçuxur	AZ		40.40	49.97	87349
Qarchak	IR		35.43	51.58	251834
Qarshi	UZ		38.86	65.79	278300
Qazvin	IR		36.27	50.00	333635
Qaşr Bin Ghashīr	LY		32.68	13.18	100069
Qeładizê	IQ		36.18	45.13	140688
Qianjiang	CN		30.42	112.89	179079
Qianjiang	CN		29.53	108.77	143727
Qiantang	CN		30.18	106.32	65894
Qiaoguan	CN		36.56	118.88	82467
Qiaotou	CN		36.94	101.67	114712
Qibao	CN		31.15	121.36	283352
Qina	EG		26.16	32.73	252883
Qincheng	CN		27.21	116.53	99987
Qingdao	CN		36.06	120.38	7172451
Qingfu	CN		28.44	104.52	56650
Qinggang	CN		29.47	106.24	78582
Qinggang	CN		46.70	126.09	64182
Qingnian	CN		36.84	115.71	110046
Qingpu	CN		31.15	121.11	1271424
Qingquan	CN		30.45	115.26	76154
Qingshuping	CN		27.38	112.02	62000
Qingxichang	CN		28.40	108.90	53552
Qingyang	CN		35.71	107.64	2125400
Qingyang	CN		37.50	121.26	65622
Qingyuan	CN		23.70	113.03	1738424
Qingzhou	CN		36.70	118.48	236406
Qinhuangdao	CN		39.94	119.59	759718
Qinnan	CN		33.25	119.91	55975
Qinzhou	CN		21.98	108.65	1296300
Qionghai	CN		19.24	110.46	528238
Qionghu	CN		28.84	112.36	66145
Qiongshan	CN		20.01	110.35	87657
Qipan	CN		34.24	118.22	66419
Qiqihar	CN		47.34	123.96	882364
Qiryat Ata	IL		32.81	35.11	59030
Qishan	CN		29.84	117.72	55500
Qishan	CN		34.63	116.80	51750
Qitaihe	CN		45.77	131.00	345033
Qiuji	CN		33.80	118.00	76343
Qods	IR		35.72	51.11	309605
Qom	IR		34.64	50.88	900000
Qonce	ZA		-32.88	27.39	93072
Qorveh	IR		35.17	47.81	87953
Qoryooley	SO		1.79	44.53	51720
Qo‘qon	UZ		40.53	70.94	259700
Quakers Hill	AU		-33.73	150.88	26904
Quanzhou	CN		24.91	118.59	1469157
Quarto Oggiaro	IT		45.51	9.14	182118
Quartu Sant'Elena	IT		39.23	9.25	66620
Quatre Bornes	MU		-20.26	57.48	77308
Qubo Saeed Khan	PK		27.87	67.71	99308
Queen Creek	US	Arizona	33.25	-111.63	34614
Queens	US	New York	40.68	-73.84	2316841
Queens Village	US	New York	40.73	-73.74	51919
Queensbury	US	New York	43.38	-73.61	27703
Queenstown	ZA		-31.90	26.88	118599
Queenstown	GB		51.48	-0.15	15599
Queenstown Estate	SG		1.29	103.80	101480
Queimados	BR		-22.72	-43.56	149093
Quelimane	MZ		-17.88	36.89	349842
Queluz	PT		38.76	-9.25	103399
Quetta	PK		30.18	67.00	1565546
Quetzaltenango	GT		14.84	-91.52	180706
Quevedo	EC		-1.03	-79.46	213842
Quezon	PH		7.73	125.10	114521
Quezon City	PH		14.65	121.05	3084270
Qufu	CN		35.60	116.99	85144
Qui Nhon	VN		13.78	109.22	519208
Quibdó	CO		5.69	-76.66	129237
Quilicura	CL		-33.37	-70.71	210410
Quillacollo	BO		-17.39	-66.28	172405
Quillota	CL		-32.88	-71.25	67779
Quilmes	AR		-34.72	-58.25	262379
Quilpué	CL		-33.05	-71.44	130263
Quimper	FR		48.00	-4.10	63849
Quincy	US	Massachusetts	42.25	-71.00	93618
Quincy	US	Illinois	39.94	-91.41	40780
Quinte West	CA		44.18	-77.57	43577
Quispamsis	CA		45.42	-65.95	18768
Quissecula	AO		-11.39	15.09	90000
Quito	EC		-0.23	-78.52	2781641
Quixadá	BR		-4.97	-39.02	84168
Quixeramobim	BR		-5.20	-39.29	82177
Qujing	CN		25.48	103.78	1408500
Qulsary	KZ		46.95	54.02	51216
Qurayyat	SA		31.33	37.34	102903
Qurayyāt	OM		23.26	58.92	63133
Quthbullapur	IN		17.50	78.46	225816
Quvasoy	UZ		40.30	71.98	96900
Quwaysinā	EG		30.56	31.16	65690
Quzhou	CN		28.96	118.87	902767
Québec	CA		46.81	-71.21	531902
Quíbor	VE		9.93	-69.62	51377
Quảng Ngãi	VN		15.12	108.79	278496
Quận Ba	VN		10.77	106.69	220375
Quận Bốn	VN		10.77	106.71	199329
Quận Mười	VN		10.77	106.67	399000
Quận Mười Một	VN		10.76	106.64	332536
Quận Năm	VN		10.76	106.67	187510
Quận Sáu	VN		10.75	106.65	271050
Quận Đức Thịnh	VN		10.31	105.74	132000
Qā’em Shahr	IR		36.47	52.87	204953
Qūchān	IR		37.11	58.51	111752
Qūş	EG		25.92	32.76	84386
Qŭnghirot	UZ		43.04	58.84	80090
Ra'anana	IL		32.18	34.87	75421
Rabak	SD		13.18	32.74	135281
Rabat	MA		34.01	-6.83	1655753
Rabkavi	IN		16.48	75.11	73835
Rabkavi-Banhatti	IN		16.47	75.12	77004
Rabwah	PK		31.76	72.91	70000
Racibórz	PL		50.09	18.22	58464
Racine	US	Wisconsin	42.73	-87.78	77742
Radcliff	US	Kentucky	37.84	-85.95	22387
Radcliffe	GB		53.56	-2.32	29950
Radford	US	Virginia	37.13	-80.58	17403
Radnor	US	Pennsylvania	40.05	-75.36	30878
Radom	PL		51.40	21.15	226794
Radès	TN		36.77	10.27	72209
Raebareli	IN		26.23	81.23	186433
Rafaela	AR		-31.25	-61.49	88713
Rafaḩ	PS		31.30	34.24	126305
Rafsanjān	IR		30.41	55.99	147680
Ragusa	IT		36.93	14.72	74251
Raha	ID		-4.84	122.72	69980
Rahim Yar Khan	PK		28.42	70.30	517000
Rahlstedt	DE		53.60	10.16	92511
Rahway	US	New Jersey	40.61	-74.28	29508
Raigarh	IN		21.90	83.40	150019
Raipur	IN		21.23	81.63	1027264
Raja Jang	PK		31.22	74.25	100000
Rajamahendravaram	IN		17.01	81.78	376333
Rajanpur	PK		29.10	70.33	50682
Rajapalayam	IN		9.45	77.55	130442
Rajgangpur	IN		22.20	84.58	51362
Rajin	KP		42.26	130.28	66224
Rajpur Sonarpur	IN		22.44	88.43	424368
Rajpura	IN		30.48	76.59	92301
Rajshahi	BD		24.37	88.60	763580
Raleigh	US	North Carolina	35.77	-78.64	482295
Ramadi	IQ		33.42	43.31	223500
Ramagundam	IN		18.75	79.47	242979
Ramanathapuram	IN		9.37	78.83	65314
Ramapuram	IN		13.03	80.18	52295
Ramat Gan	IL		32.08	34.81	170822
Ramenki	RU		55.70	37.50	130000
Ramenskoye	RU		55.56	38.24	96000
Ramiros	AO		-9.06	13.05	323576
Ramla	IL		31.93	34.86	76246
Ramna Maidan	BD		23.73	90.40	143677
Ramona	US	California	33.04	-116.87	20292
Ramos Arizpe	MX		25.54	-100.95	66554
Rampur Hat	IN		24.18	87.78	53468
Rampura Phul	IN		30.28	75.24	51023
Ramsbottom	GB		53.65	-2.32	17067
Ramsey	US	Minnesota	45.26	-93.45	25828
Ramsey	US	New Jersey	41.06	-74.14	15102
Ramsgate	GB		51.34	1.42	42027
Rancagua	CL		-34.17	-70.74	212695
Ranchi	IN		23.34	85.31	1120374
Rancho Cordova	US	California	38.59	-121.30	71017
Rancho Cucamonga	US	California	34.11	-117.59	175236
Rancho Mirage	US	California	33.74	-116.41	18083
Rancho Palos Verdes	US	California	33.74	-118.39	42732
Rancho Penasquitos	US	California	32.96	-117.12	60000
Rancho San Diego	US	California	32.75	-116.94	21208
Rancho Santa Margarita	US	California	33.64	-117.60	49324
Randallstown	US	Maryland	39.37	-76.80	32430
Randburg	ZA		-26.09	28.00	337053
Randers	DK		56.46	10.04	62802
Randfontein	ZA		-26.18	27.70	133654
Randolph	US	Massachusetts	42.16	-71.04	32112
Randolph	US	New Jersey	40.85	-74.58	25734
Randwick	AU		-33.91	151.25	28943
Ranebennur	IN		14.62	75.63	106406
Rangamati	BD		22.64	92.19	106069
Rangel	AO		-8.83	13.26	190569
Rangiora	NZ		-43.30	172.58	19300
Rangkasbitung	ID		-6.36	106.25	137041
Rangpur	BD		25.75	89.25	1031388
Rantauprapat	ID		2.10	99.83	103009
Rapid City	US	South Dakota	44.08	-103.23	73569
Raposo Tavares	BR		-23.59	-46.79	117738
Ras Al Khaimah	AE		25.79	55.94	351943
Ras Tanura	SA		26.71	50.07	62314
Rasapūdipalem	IN		17.73	83.32	1728128
Rasht	IR		37.28	49.59	594590
Rasipuram	IN		11.46	78.19	50244
Rat Burana	TH		13.68	100.51	86695
Ratangarh	IN		28.08	74.62	71124
Ratchaburi	TH		13.54	99.82	92448
Ratchathewi	TH		13.76	100.53	73035
Rathfarnham	IE		53.30	-6.28	17333
Ratingen	DE		51.30	6.85	91606
Ratlām	IN		23.33	75.04	264914
Ratnagiri	IN		16.99	73.31	76229
Ratodero	PK		27.80	68.29	81935
Raurkela Industrial Township	IN		22.20	84.86	216410
Ravenna	IT		44.41	12.20	80868
Rawalakot	PK		33.86	73.76	50000
Rawalpindi	PK		33.60	73.05	3357612
Rawang	MY		3.32	101.58	199095
Rawmarsh	GB		53.46	-1.34	18498
Rawson	AR		-31.58	-68.54	130258
Rawtenstall	GB		53.70	-2.28	23000
Raxaul	IN		26.98	84.85	55536
Rayachoti	IN		14.06	78.75	91234
Rayleigh	GB		51.59	0.60	32380
Raymore	US	Missouri	38.80	-94.45	20374
Rayon KTZ	UA		49.94	36.37	200000
Rayong	TH		12.68	101.26	106737
Raytown	US	Missouri	39.01	-94.46	29401
Ra’s Bayrūt	LB		33.90	35.48	1251739
Reading	GB		51.46	-0.97	318014
Reading	US	Pennsylvania	40.34	-75.93	87879
Reading	US	Massachusetts	42.53	-71.10	24747
Recanto das Emas	BR		-15.91	-48.06	115550
Rechytsa	BY		52.36	30.39	64733
Recife	BR		-8.05	-34.88	1653461
Recklinghausen	DE		51.61	7.20	122438
Reconquista	AR		-29.15	-59.65	90184
Red Deer	CA		52.27	-113.80	100844
Red Wing	US	Minnesota	44.56	-92.53	16445
Redan	US	Georgia	33.75	-84.13	33015
Redbank Plains	AU		-27.65	152.86	19094
Redcar	GB		54.62	-1.06	37073
Redding	US	California	40.59	-122.39	91582
Redditch	GB		52.31	-1.95	87847
Redenção	BR		-8.03	-50.03	85597
Redford	US	Michigan	42.38	-83.30	49936
Redhill	GB		51.24	-0.17	51559
Redland	US	Maryland	39.15	-77.14	17242
Redlands	US	California	34.06	-117.18	71035
Redmond	US	Washington	47.67	-122.12	60598
Redmond	US	Oregon	44.27	-121.17	28654
Redondo Beach	US	California	33.85	-118.39	68166
Redruth	GB		50.23	-5.22	42690
Redwood City	US	California	37.49	-122.24	85288
Reedley	US	California	36.60	-119.45	25569
Reef Al Fujairah City	AE		25.14	56.25	82310
Regensburg	DE		49.02	12.10	151389
Reggio Calabria	IT		38.11	15.66	182455
Reggio nell'Emilia	IT		44.70	10.63	171944
Reghaïa	DZ		36.74	3.34	54962
Regina	CA		50.45	-104.62	226404
Registro	BR		-24.49	-47.84	59947
Rego Park	US	New York	40.73	-73.85	43925
Reẖovot	IL		31.89	34.81	149392
Reigate	GB		51.24	-0.21	21820
Reims	FR		49.27	4.03	196565
Reinickendorf	DE		52.56	13.34	83972
Reisterstown	US	Maryland	39.47	-76.83	25968
Relizane	DZ		35.74	0.56	123255
Remedios de Escalada de San Martín	AR		-34.73	-58.40	81465
Remscheid	DE		51.18	7.19	117118
Remuera	NZ		-36.88	174.80	27810
Renala Khurd	PK		30.88	73.60	100054
Renca	CL		-33.40	-70.71	147151
Renfrew	GB		55.87	-4.39	24270
Renfrew Heights	CA		49.25	-123.03	20570
Renfrew-Collingwood	CA		49.24	-123.04	51530
Rengasdengklok	ID		-6.16	107.30	201463
Rennes	FR		48.11	-1.67	227830
Reno	US	Nevada	39.53	-119.81	264165
Renqiu	CN		38.71	116.10	98569
Renton	US	Washington	47.48	-122.22	100242
Renukūt	IN		24.22	83.04	62413
Renzhao	CN		36.64	120.20	64569
Repalle	IN		16.02	80.83	50866
Repentigny	CA		45.74	-73.45	84965
Republic	US	Missouri	37.12	-93.48	16005
Republica	BR		-23.54	-46.64	60720
Reseda	US	California	34.20	-118.54	65000
Resende	BR		-22.47	-44.45	111514
Reservoir	AU		-37.72	145.00	51096
Resistencia	AR		-27.46	-58.99	290793
Ressano Garcia	MZ		-25.44	32.00	110000
Reston	US	Virginia	38.97	-77.34	58404
Retalhuleu	GT		14.54	-91.68	90505
Retford	GB		53.32	-0.94	22023
Retiro	ES		40.41	-3.68	126058
Reus	ES		41.16	1.11	103477
Reutlingen	DE		48.49	9.20	112627
Reutov	RU		55.76	37.86	78370
Revda	RU		56.80	59.94	61785
Revere	US	Massachusetts	42.41	-71.01	53422
Rewa	IN		24.53	81.29	235654
Rewāri	IN		28.20	76.62	143021
Rexburg	US	Idaho	43.83	-111.79	27663
Reyhanlı	TR		36.27	36.57	56995
Reykjavík	IS		64.14	-21.90	118918
Reynoldsburg	US	Ohio	39.95	-82.81	37158
Reynosa	MX		26.08	-98.28	589466
Reşiţa	RO		45.30	21.89	81228
Rhawnhurst	US	Pennsylvania	40.06	-75.06	25581
Rheine	DE		52.29	7.44	76491
Rheinhausen	DE		51.40	6.71	78203
Rhondda	GB		51.66	-3.45	69506
Rhosllannerchrugog	GB		53.01	-3.06	25362
Rhyl	GB		53.32	-3.49	25874
Riacho Fundo II	BR		-15.90	-48.05	105210
Rialto	US	California	34.11	-117.37	103132
Ribeira do Pombal	BR		-10.83	-38.54	54010
Ribeirão das Neves	BR		-19.77	-44.09	329794
Ribeirão Pires	BR		-23.71	-46.41	115559
Ribeirão Preto	BR		-21.18	-47.81	698642
Riberalta	BO		-11.01	-66.05	99070
Richard-Toll	SN		16.46	-15.70	73147
Richards Bay	ZA		-28.78	32.04	252968
Richardson	US	Texas	32.95	-96.73	110815
Richfield	US	Minnesota	44.88	-93.28	36216
Richland	US	Washington	46.29	-119.28	54248
Richmond	US	Virginia	37.55	-77.46	226610
Richmond	CA		49.17	-123.14	209937
Richmond	US	California	37.94	-122.35	109708
Richmond	US	Indiana	39.83	-84.89	35854
Richmond	US	Kentucky	37.75	-84.29	33533
Richmond	AU		-37.82	145.00	28587
Richmond	GB		51.46	-0.31	21469
Richmond	NZ		-41.33	173.18	19950
Richmond Hill	CA		43.87	-79.44	202022
Richmond Hill	US	New York	40.70	-73.83	98984
Richmond West	US	Florida	25.61	-80.43	35884
Rickmansworth	GB		51.64	-0.48	25413
Ridder	KZ		50.35	83.52	52664
Ridgecrest	US	California	35.62	-117.67	28780
Ridgeland	US	Mississippi	32.43	-90.13	24351
Ridgewood	US	New York	40.70	-73.91	69317
Ridgewood	US	New Jersey	40.98	-74.12	25621
Riga	LV		56.95	24.11	742572
Rijeka	HR		45.33	14.44	107964
Rikaze	CN		29.25	88.88	80000
Riley Park	CA		49.24	-123.09	22555
Rimini	IT		44.06	12.57	148688
Rimouski	CA		48.45	-68.52	42240
Ringwood	AU		-37.82	145.23	19144
Rio Bonito	BR		-22.71	-42.61	59113
Rio Branco	BR		-9.97	-67.81	419452
Rio Claro	BR		-22.41	-47.56	201418
Rio das Ostras	BR		-22.53	-41.95	168099
Rio de Janeiro	BR		-22.91	-43.18	6747815
Rio de Mouro	PT		38.77	-9.33	54695
Rio do Sul	BR		-27.21	-49.64	72587
Rio Grande	BR		-32.03	-52.10	187838
Rio Largo	BR		-9.48	-35.85	97435
Rio Linda	US	California	38.69	-121.45	15106
Rio Pequeno	BR		-23.57	-46.76	131631
Rio Rancho	US	New Mexico	35.23	-106.66	87521
Rio Rico	US	Arizona	31.47	-110.98	18962
Rio Verde	BR		-17.80	-50.93	225696
Riobamba	EC		-1.67	-78.66	264048
Riohacha	CO		11.54	-72.91	188014
Rionegro	CO		6.16	-75.37	128153
Rioverde	MX		21.93	-99.99	53128
Ripley	GB		53.03	-1.40	21097
Ripon	GB		54.14	-1.53	16363
Ripon	US	California	37.74	-121.12	15151
Risca	GB		51.61	-3.10	20443
Rishon LeTsiyyon	IL		31.97	34.79	258535
Rishra	IN		22.72	88.35	117014
Rishīkesh	IN		30.11	78.29	66390
Rittenhouse	US	Pennsylvania	39.95	-75.17	21582
Rittō	JP		35.03	136.00	70312
Rivas-Vaciamadrid	ES		40.33	-3.51	68405
River Falls	US	Wisconsin	44.86	-92.62	15269
Rivera	UY		-30.91	-55.55	84775
Riverbank	US	California	37.74	-120.94	24122
Riverdale	US	Georgia	33.57	-84.41	15989
Riverside	US	California	33.95	-117.40	317261
Riverside	US	Ohio	39.78	-84.12	24972
Riverton	US	Utah	40.52	-111.94	41900
Riverview	US	Florida	27.87	-82.33	71050
Riverview	CA		46.05	-64.82	20584
Riviera Beach	US	Florida	26.78	-80.06	34005
Rivière-des-Prairies–Pointe-aux-Trembles	CA		45.64	-73.58	113868
Rivière-du-Loup	CA		47.83	-69.54	18586
Rivne	UA		50.62	26.24	243873
Riyadh	SA		24.69	46.72	4205961
Rize	TR		41.02	40.52	119828
Rizhao	CN		35.41	119.53	661943
Road Town	VG		18.43	-64.62	8449
Roanoke	US	Virginia	37.27	-79.94	100011
Roanoke Rapids	US	North Carolina	36.46	-77.65	15345
Robertsonpet	IN		12.96	78.28	162230
Robina	AU		-28.07	153.39	23140
Robāţ Karīm	IR		35.48	51.08	105393
Rochdale	GB		53.62	-2.16	97550
Rochedale South	AU		-27.60	153.12	15073
Rochester	US	New York	43.15	-77.62	209802
Rochester	US	Minnesota	44.02	-92.47	112225
Rochester	US	New Hampshire	43.30	-70.98	30038
Rochester	GB		51.39	0.51	28671
Rochester Hills	US	Michigan	42.66	-83.15	73424
Rochford	GB		51.58	0.71	16739
Rock Forest	CA		45.36	-72.00	35500
Rock Hill	US	South Carolina	34.92	-81.03	71548
Rock Island	US	Illinois	41.51	-90.58	38620
Rock Springs	US	Wyoming	41.59	-109.20	23962
Rockcliffe-Smythe	CA		43.67	-79.49	22246
Rockdale	AU		-33.95	151.13	15436
Rockford	US	Illinois	42.27	-89.09	148278
Rockhampton	AU		-23.38	150.51	81021
Rockingham	AU		-32.28	115.73	15312
Rockland	US	Massachusetts	42.13	-70.92	17982
Rockledge	US	Florida	28.35	-80.73	24926
Rocklin	US	California	38.79	-121.24	61213
Rockville	US	Maryland	39.08	-77.15	66980
Rockville Centre	US	New York	40.66	-73.64	24201
Rockwall	US	Texas	32.93	-96.46	42566
Rocky Mount	US	North Carolina	35.94	-77.79	55806
Rocky River	US	Ohio	41.48	-81.84	20376
Rodenkirchen	DE		50.89	6.99	110158
Rodriguez	PH		14.76	121.20	134432
Roehampton	GB		51.45	-0.24	16132
Roeselare	BE		50.95	3.12	56016
Rogers	US	Arkansas	36.33	-94.12	63159
Rogers Park	US	Illinois	42.01	-87.67	54402
Roha	IN		18.44	73.12	90000
Rohini	IN		28.74	77.07	860000
Rohnert Park	US	California	38.34	-122.70	42407
Rohri	PK		27.69	68.90	92135
Rohtak	IN		28.89	76.59	374292
Rolim de Moura	BR		-11.80	-61.80	56406
Rolla	US	Missouri	37.95	-91.77	20019
Rolleston	NZ		-43.58	172.38	34100
Rolling Meadows	US	Illinois	42.08	-88.01	24190
Rolândia	BR		-23.31	-51.37	71670
Roman	RO		46.92	26.93	67819
Rome	IT		41.89	12.51	2318895
Rome	US	Georgia	34.26	-85.16	36323
Rome	US	New York	43.21	-75.46	32573
Romeoville	US	Illinois	41.65	-88.09	39719
Romford	GB		51.58	0.19	95000
Romsey	GB		50.99	-1.50	17161
Romulus	US	Michigan	42.22	-83.40	23417
Rondon do Pará	BR		-4.78	-48.07	53143
Rondonópolis	BR		-16.47	-54.64	259167
Ronkonkoma	US	New York	40.82	-73.14	19082
Roodepoort	ZA		-26.16	27.87	326416
Roorkee	IN		29.87	77.89	103894
Roosendaal	NL		51.53	4.47	77725
Roosevelt	US	New York	40.68	-73.59	16258
Ropar	IN		30.97	76.53	56038
Roquetas de Mar	ES		36.76	-2.61	94925
Rosales	PH		15.89	120.63	67510
Rosamond	US	California	34.86	-118.16	18150
Rosario	AR		-32.95	-60.64	948312
Rosario	PH		13.63	121.22	128352
Rosarito	MX		32.36	-117.05	100660
Rose Hill	US	Virginia	38.79	-77.11	20226
Roseau	DM		15.30	-61.39	16571
Roseburg	US	Oregon	43.22	-123.34	22114
Rosedale	US	New York	40.66	-73.74	25812
Rosedale	US	Maryland	39.32	-76.52	19257
Rosedale-Moore Park	CA		43.68	-79.38	20923
Roselle	US	Illinois	41.98	-88.08	22994
Roselle	US	New Jersey	40.65	-74.26	21670
Rosemead	US	California	34.08	-118.07	54908
Rosemont	US	California	38.55	-121.36	22681
Rosemont–La Petite-Patrie	CA		45.54	-73.61	146501
Rosemount	US	Minnesota	44.74	-93.13	23413
Rosenberg	US	Texas	29.56	-95.81	35510
Rosenheim	DE		47.86	12.12	60167
Rosetta	EG		31.40	30.42	301795
Roseville	US	California	38.75	-121.29	130269
Roseville	US	Michigan	42.50	-82.94	47637
Roseville	US	Minnesota	45.01	-93.16	35580
Rosh Ha‘Ayin	IL		32.10	34.96	72881
Roshanpura	IN		28.60	76.99	57217
Roskilde	DK		55.64	12.08	51916
Roslavl’	RU		53.95	32.86	56971
Roslindale	US	Massachusetts	42.29	-71.12	27683
Rossendale	GB		53.68	-2.28	67400
Rossosh’	RU		51.12	38.51	64323
Rossosh’	RU		50.20	39.57	62000
Rossville	US	New York	40.55	-74.21	18792
Rossville	US	Maryland	39.34	-76.48	15147
Rostock	DE		54.09	12.14	198293
Rostov-on-Don	RU		47.22	39.71	1130305
Roswell	US	Georgia	34.02	-84.36	94501
Roswell	US	New Mexico	33.39	-104.52	48544
Rotherham	GB		53.43	-1.36	117618
Rotorua	NZ		-38.14	176.25	65901
Rotterdam	NL		51.92	4.48	868135
Rotterdam	US	New York	42.79	-73.97	20652
Rottingdean	GB		50.81	-0.06	21756
Roubaix	FR		50.69	3.17	99507
Rouen	FR		49.44	1.10	116331
Rouge	CA		43.80	-79.17	46496
Rouiba	DZ		36.74	3.28	117558
Rouissat	DZ		31.92	5.35	80784
Round Lake	US	Illinois	42.35	-88.09	18461
Round Lake Beach	US	Illinois	42.37	-88.09	27852
Round Rock	US	Texas	30.51	-97.68	115997
Rourkela	IN		22.22	84.86	273317
Rouyn-Noranda	CA		48.24	-79.02	23504
Rovaniemi	FI		66.50	25.69	65670
Rovigo	IT		45.07	11.79	50279
Rowland Heights	US	California	33.98	-117.91	48993
Rowlett	US	Texas	32.90	-96.56	60236
Rowville	AU		-37.93	145.23	33571
Roxas City	PH		11.59	122.75	185236
Roxburgh Park	AU		-37.63	144.93	24129
Roxbury Crossing	US	Massachusetts	42.33	-71.09	15248
Roy	US	Utah	41.16	-112.03	37964
Royal Leamington Spa	GB		52.29	-1.52	50923
Royal Oak	US	Michigan	42.49	-83.14	59008
Royal Palm Beach	US	Florida	26.71	-80.23	37633
Royal Tunbridge Wells	GB		51.13	0.26	68910
Royston	GB		52.05	-0.02	15781
Royton	GB		53.57	-2.12	22848
Rubidoux	US	California	34.00	-117.41	34280
Rubio	VE		7.70	-72.36	93197
Rubizhne	UA		49.01	38.38	55247
Rubtsovsk	RU		51.51	81.21	161065
Rubí	ES		41.49	2.03	72987
Ruda Śląska	PL		50.26	18.86	146189
Rudnyy	KZ		52.97	63.11	124000
Rudrapur	IN		28.98	79.40	154554
Rueil-Malmaison	FR		48.88	2.19	76616
Rufisque	SN		14.72	-17.27	295459
Rufisque est	SN		14.72	-17.27	221066
Rugao	CN		32.37	120.58	257400
Rugby	GB		52.37	-1.26	78117
Rugeley	GB		52.76	-1.94	26156
Ruiru	KE		-1.15	36.96	490120
Ruislip	GB		51.57	-0.42	31000
Rui’an	CN		27.78	120.66	927383
Rukban	JO		33.31	38.70	85000
Rumonge	BI		-3.97	29.44	55599
Runan	CN		33.00	114.35	60202
Runcorn	GB		53.34	-2.73	61145
Rundu	NA		-17.92	19.77	75180
Ruqi	SO		9.97	43.43	148702
Ruse	BG		43.85	25.95	121168
Rushden	GB		52.29	-0.60	37584
Ruskin	US	Florida	27.72	-82.43	17208
Russas	BR		-4.94	-37.98	72928
Russeifa	JO		32.02	36.05	268237
Russellville	US	Arkansas	35.28	-93.13	29166
Rustaq	OM		23.39	57.42	120000
Rustavi	GE		41.56	44.98	128249
Rustenburg	ZA		-25.67	27.24	373695
Ruston	US	Louisiana	32.52	-92.64	22340
Rutchenkivskyi	UA		47.98	37.70	168029
Rutherford	US	New Jersey	40.83	-74.11	18690
Rutherglen	GB		55.83	-4.21	30950
Rutland	CA		49.90	-119.39	34800
Rutland	US	Vermont	43.61	-72.97	15824
Rutoma	UG		-0.57	30.38	86100
Rutshuru	CD		-1.19	29.45	82680
Ruwa	ZW		-17.89	31.24	94083
Ryazanskiy	RU		55.73	37.77	101000
Ryazan’	RU		54.63	39.70	538962
Rybatskoye	RU		59.84	30.50	55076
Rybinsk	RU		58.05	38.84	216724
Rybnik	PL		50.10	18.54	142510
Ryde	AU		-33.82	151.11	26385
Ryde	GB		50.73	-1.16	24096
Rye	US	New York	40.98	-73.68	16046
Ryton	GB		52.62	-2.35	16093
Ryūgasaki	JP		35.90	140.18	85761
Rzeszów	PL		50.04	22.00	198317
Rzhev	RU		56.26	34.33	62246
Râmnicu Vâlcea	RO		45.10	24.37	93151
Río Cuarto	AR		-33.13	-64.35	157010
Río Gallegos	AR		-51.63	-69.25	95796
Río Grande	AR		-53.79	-67.71	52681
Río Tercero	AR		-32.18	-64.11	53389
Rîbniţa	MD		47.77	29.01	55455
Ródos	GR		36.44	28.22	56128
Rüsselsheim am Main	DE		49.99	8.42	59730
Rābigh	SA		22.80	39.03	72928
Rāghogarh	IN		24.44	77.20	63873
Rāichūr	IN		16.21	77.36	234073
Rāiganj	IN		25.61	88.12	170252
Rāipur	BD		23.04	90.77	64652
Rāj-Nāndgaon	IN		21.10	81.03	163114
Rājbirāj	NP		26.54	86.75	69803
Rājgarh	IN		28.64	75.39	59193
Rājkot	IN		22.29	70.79	1390640
Rājsamand	IN		25.07	73.88	67798
Rāmganj	BD		23.10	90.85	55241
Rāmgarh	IN		23.63	85.52	88781
Rāmgundam	IN		18.80	79.45	452261
Rāmhormoz	IR		31.28	49.60	74285
Rāmnagar	IN		29.39	79.13	51244
Rāmpur	IN		28.81	79.03	296418
Rāniganj	IN		17.43	78.49	217910
Rānipet	IN		12.92	79.33	264330
Rānyah	IQ		36.26	44.88	114173
Rānāghāt	IN		23.18	88.57	70984
Rānīganj	IN		23.62	87.13	131261
Rāth	IN		25.59	79.57	61728
Rāyadrug	IN		14.70	76.85	61749
Rāyagada	IN		19.17	83.41	71208
Rāzampeta	IN		14.20	79.16	54050
Rạch Giá	VN		10.01	105.08	459860
Sa Dec	VN		10.29	105.76	214610
Sa'dah	YE		16.94	43.76	51870
Saaba	BF		12.37	-1.41	136011
Saanich	CA		48.55	-123.37	117735
Saarbrücken	DE		49.23	7.01	182971
Sabadell	ES		41.54	2.11	211734
Sabae	JP		35.95	136.18	68302
Sabanalarga	CO		10.63	-74.92	102334
Sabaneta	CO		6.15	-75.62	82375
Sabará	BR		-19.89	-43.81	129380
Sabha	LY		27.04	14.43	149329
Sabinas	MX		27.86	-101.12	54905
Sablayan	PH		12.83	120.77	91406
Sabt Alalayah	SA		19.58	41.96	100000
Sabzevar	IR		36.21	57.68	243700
Sacaba	BO		-17.40	-66.04	180726
Sachse	US	Texas	32.98	-96.60	24554
Saco	US	Maine	43.50	-70.44	19078
Sacomã	BR		-23.63	-46.60	261436
Sacramento	US	California	38.58	-121.49	524943
Saddiqabad	PK		28.31	70.13	274210
Saddle Ridge	CA		51.13	-113.95	24365
Saddleworth	GB		53.55	-2.00	25441
Sado	JP		38.02	138.36	51492
Sadr City	IQ		33.39	44.46	1211849
Safaga	EG		26.75	33.94	53639
Safety Harbor	US	Florida	27.99	-82.69	17454
Saffron Walden	GB		52.02	0.24	16610
Safi	MA		32.30	-9.24	336883
Saga	JP		33.23	130.30	233301
Sagaing	MM		21.88	95.98	78739
Sagamihara	JP		35.57	139.24	720780
Sagay	PH		10.94	123.42	72153
Saginaw	US	Michigan	43.42	-83.95	49347
Saginaw	US	Texas	32.86	-97.36	22079
Saginaw Township North	US	Michigan	43.46	-84.01	24994
Sagrada Família	ES		41.40	2.17	51623
Sagua la Grande	CU		22.81	-80.07	62073
Saguenay	CA		48.42	-71.07	148886
Sagunto	ES		39.68	-0.27	66070
Sahagún	CO		8.95	-75.44	59188
Sahand	IR		37.95	46.11	82494
Saharsa	IN		25.87	86.60	156540
Sahaswān	IN		28.07	78.75	60953
Sahiwal	PK		31.97	72.33	538344
Sahiwal	PK		30.67	73.10	538344
Sahuarita	US	Arizona	31.96	-110.96	25707
Sahuayo de Morelos	MX		20.06	-102.72	64431
Sahāranpur	IN		29.97	77.55	484873
Sai Mai	TH		13.92	100.65	188123
Saidpur	BD		25.78	88.89	199422
Saijō	JP		33.92	133.18	104791
Saiki	JP		32.95	131.90	66851
Saint Albans	AU		-37.73	144.80	35091
Saint Andrews	US	South Carolina	34.04	-81.10	21151
Saint Andrews	GB		56.34	-2.80	18410
Saint Charles	US	Missouri	38.78	-90.48	65794
Saint Charles	US	Maryland	38.60	-76.94	36376
Saint Clair Shores	US	Michigan	42.50	-82.89	59715
Saint Cloud	US	Minnesota	45.56	-94.16	65842
Saint Cloud	US	Florida	28.25	-81.28	35183
Saint Croix	VI		17.73	-64.75	50601
Saint George	US	Utah	37.10	-113.58	72897
Saint Helier	JE		49.19	-2.10	28000
Saint Ives	AU		-33.73	151.16	18384
Saint Ives	GB		52.33	-0.08	16815
Saint John	CA		45.27	-66.06	71808
Saint John West	CA		45.26	-66.08	15255
Saint John’s	AG		17.12	-61.84	51737
Saint Joseph	US	Missouri	39.77	-94.85	76780
Saint Kilda	AU		-37.87	144.98	19490
Saint Louis Park	US	Minnesota	44.95	-93.35	45250
Saint Matthews	US	Kentucky	38.25	-85.66	17472
Saint Michael	US	Minnesota	45.21	-93.66	16399
Saint Neots	GB		52.22	-0.27	30811
Saint Paul	US	Minnesota	44.94	-93.09	303176
Saint Peters	GB		51.37	1.42	125370
Saint Peters	US	Missouri	38.80	-90.63	52575
Saint Petersburg	RU		59.94	30.31	5351935
Saint-André	RE		-20.96	55.65	57150
Saint-Augustin-de-Desmaures	CA		46.74	-71.45	17281
Saint-Basile-le-Grand	CA		45.53	-73.28	15605
Saint-Brieuc	FR		48.52	-2.77	52774
Saint-Bruno-de-Montarville	CA		45.53	-73.35	24388
Saint-Charles-Borromée	CA		46.05	-73.47	15285
Saint-Constant	CA		45.37	-73.57	27359
Saint-Denis	RE		-20.88	55.45	154765
Saint-Denis	FR		48.94	2.35	96128
Saint-Eustache	CA		45.56	-73.91	42062
Saint-Georges	CA		46.11	-70.67	31173
Saint-Gilles	BE		50.83	4.34	50221
Saint-Henri	CA		45.47	-73.60	15800
Saint-Hubert	CA		45.50	-73.42	82548
Saint-Hyacinthe	CA		45.63	-72.96	50326
Saint-Jean-sur-Richelieu	CA		45.31	-73.26	98036
Saint-Jérôme	CA		45.78	-74.00	54948
Saint-Laurent	CA		45.50	-73.67	98828
Saint-Lazare	CA		45.40	-74.13	19889
Saint-Lin-Laurentides	CA		45.85	-73.77	17463
Saint-Louis	SN		16.02	-16.49	254171
Saint-Louis	RE		-21.29	55.41	53935
Saint-Louis-de-Terrebonne	CA		45.70	-73.79	119944
Saint-Léonard	CA		45.59	-73.60	79495
Saint-Malo	FR		48.65	-2.01	50676
Saint-Marc	HT		19.11	-72.70	266642
Saint-Maur-des-Fossés	FR		48.79	2.49	75402
Saint-Michel	CA		45.57	-73.62	56420
Saint-Michel de l'Atalaye	HT		19.37	-72.33	95216
Saint-Nazaire	FR		47.28	-2.22	67054
Saint-Paul	RE		-21.01	55.27	105240
Saint-Pierre	RE		-21.34	55.48	84077
Saint-Pierre	PM		46.78	-56.18	6200
Saint-Quentin	FR		49.85	3.29	55407
Saint-Quentin-en-Yvelines	FR		48.77	2.02	146598
Saint-Vincent-de-Paul	CA		45.62	-73.65	15194
Saint-Étienne	FR		45.43	4.39	176280
Sainte-Catherine	CA		45.40	-73.58	16762
Sainte-Catherine	CA		46.32	-72.57	16211
Sainte-Foy	CA		46.78	-71.29	111300
Sainte-Julie	CA		45.58	-73.33	29019
Sainte-Thérèse	CA		45.64	-73.83	25224
Saipan	MP		15.21	145.75	48220
Saitama	JP		35.91	139.66	1324854
Sakado	JP		35.96	139.39	100275
Sakai	JP		34.58	135.47	826161
Sakai	JP		36.15	136.19	92210
Sakaidechō	JP		34.32	133.84	57090
Sakakah	SA		29.97	40.21	128332
Sakata	JP		38.92	139.85	100273
Saki	NG		8.67	3.39	178677
Sakiet ed Daier	TN		34.79	10.81	125204
Sakiet ez Zit	TN		34.80	10.76	100000
Sakon Nakhon	TH		17.16	104.15	76237
Sakrand	PK		26.14	68.27	72040
Saku	JP		36.22	138.48	99131
Sakura	JP		35.72	140.23	173740
Sakurai	JP		34.50	135.85	58386
Salaberry-de-Valleyfield	CA		45.25	-74.13	42787
Salamanca	MX		20.57	-101.20	160682
Salamanca	ES		40.43	-3.68	147707
Salamanca	ES		40.97	-5.66	144825
Salamá	GT		15.10	-90.32	65275
Salaqi	CN		40.54	110.51	104090
Salatiga	ID		-7.33	110.49	198971
Salavat	RU		53.38	55.91	159893
Saldanha	ZA		-33.01	17.94	68284
Sale	GB		53.43	-2.32	62550
Salem	IN		11.65	78.16	917414
Salem	US	Oregon	44.94	-123.04	175535
Salem	US	Massachusetts	42.52	-70.90	42869
Salem	US	New Hampshire	42.79	-71.20	29549
Salem	US	Virginia	37.29	-80.05	25432
Salerno	IT		40.68	14.79	125797
Salford	GB		53.49	-2.29	129794
Salgueiro	BR		-8.07	-39.12	62372
Salihli	TR		38.48	28.15	119311
Salina	US	Kansas	38.84	-97.61	47813
Salina Cruz	MX		16.18	-95.19	84438
Salinas	US	California	36.68	-121.66	157380
Salisbury	GB		51.07	-1.80	44748
Salisbury	US	North Carolina	35.67	-80.47	34017
Salisbury	US	Maryland	38.36	-75.60	32899
Salmon Arm	CA		50.70	-119.27	19432
Salmon Creek	US	Washington	45.71	-122.65	19686
Salmās	IR		38.20	44.77	81606
Salo	FI		60.38	23.13	50794
Salt Lake City	US	Utah	40.76	-111.89	215548
Salta	AR		-24.81	-65.42	520683
Saltash	GB		50.41	-4.23	15566
Saltillo	MX		25.43	-100.98	709671
Saltivka	UA		50.02	36.35	409300
Salto	BR		-23.20	-47.29	119736
Salto	UY		-31.39	-57.96	114084
Salvador	BR		-12.98	-38.49	2711840
Salvaleón de Higüey	DO		18.62	-68.71	123787
Salzburg	AT		47.80	13.04	157245
Salzgitter	DE		52.16	10.42	104970
Salé	MA		34.05	-6.80	972299
Salé Al Jadida	MA		34.00	-6.74	200000
Sal’sk	RU		46.47	41.54	61000
Samambaia	BR		-15.88	-48.10	218840
Samandağ	TR		36.08	35.98	123447
Samannūd	EG		30.96	31.24	87921
Samar	UA		48.63	35.26	70550
Samara	RU		53.21	50.14	1163399
Samara	ET		11.79	41.01	50000
Samarinda	ID		-0.49	117.15	865306
Samarkand	UZ		39.65	66.96	595200
Samba	AO		-8.88	13.20	364986
Sambalpur	IN		21.47	83.98	189366
Sambava	MG		-14.27	50.17	89003
Sambhal	IN		28.58	78.57	196109
Sambizanga	AO		-8.79	13.28	177808
Sambrial	PK		32.48	74.35	119571
Samch’ŏn	KP		38.36	125.33	86042
Samfya	ZM		-11.36	29.56	51309
Sammamish	US	Washington	47.64	-122.08	52253
Sampang	ID		-7.19	113.24	53269
Sampit	ID		-2.53	112.95	166773
Samsun	TR		41.28	36.34	394050
Samut Prakan	TH		13.60	100.60	388920
Samut Sakhon	TH		13.55	100.27	63498
Samālūţ	EG		28.31	30.71	142009
Samāna	IN		30.15	76.20	54072
Samāstipur	IN		25.86	85.78	67925
Samā’il	OM		23.30	57.95	80538
San	ML		13.30	-4.90	103227
San Andrés	CO		12.58	-81.70	58257
San Andrés Tuxtla	MX		18.45	-95.21	61769
San Angelo	US	Texas	31.46	-100.44	99893
San Antonio	US	Texas	29.42	-98.49	1526656
San Antonio	CL		-33.59	-71.61	87675
San Antonio	PY		-25.42	-57.55	55754
San Antonio de Los Altos	VE		10.39	-66.95	63873
San Antonio del Táchira	VE		7.81	-72.44	66392
San Bartolomé de Tirajana	ES		27.92	-15.57	53588
San Benito	US	Texas	26.13	-97.63	24496
San Bernardino	US	California	34.11	-117.29	216108
San Bernardino Tlaxcalancingo	MX		19.03	-98.28	54517
San Bernardo	CL		-33.59	-70.70	249858
San Blas-Canillejas	ES		40.44	-3.62	157367
San Bruno	US	California	37.63	-122.41	43185
San Carlo All'Arena	IT		40.87	14.26	69094
San Carlos	VE		9.66	-68.59	120375
San Carlos	US	California	37.51	-122.26	29931
San Carlos de Bariloche	AR		-41.15	-71.31	95394
San Carlos del Zulia	VE		9.00	-71.93	126353
San Carlos Park	US	Florida	26.47	-81.80	16824
San Chaung	MM		17.10	96.10	99619
San Clemente	US	California	33.43	-117.61	65526
San Cristobal	CU		22.72	-83.06	59579
San Cristóbal	VE		7.77	-72.24	289852
San Cristóbal	DO		18.42	-70.11	154040
San Cristóbal de las Casas	MX		16.73	-92.64	215874
San Diego	US	California	32.72	-117.16	1404452
San Dimas	US	California	34.11	-117.81	34630
San Felipe	VE		10.34	-68.74	206270
San Felipe	CL		-32.75	-70.73	59294
San Fernando	PH		15.03	120.68	251248
San Fernando	ES		36.48	-6.20	95174
San Fernando	PH		16.62	120.32	83003
San Fernando	PE		-8.40	-74.54	67844
San Fernando	TT		10.28	-61.47	55419
San Fernando	US	California	34.28	-118.44	24931
San Fernando de Apure	VE		7.89	-67.47	229197
San Francisco	US	California	37.77	-122.42	827526
San Francisco	PH		8.54	125.95	79718
San Francisco	AR		-31.42	-62.08	59062
San Francisco	CR		9.99	-84.13	55923
San Francisco De Borja	PE		-12.09	-77.00	105076
San Francisco de Macorís	DO		19.29	-70.25	124763
San Francisco del Rincón	MX		21.02	-101.86	71139
San Francisco El Alto	GT		14.94	-91.44	57894
San Francisco Tesistán	MX		20.80	-103.48	62397
San Gabriel	US	California	34.10	-118.11	40424
San Ildefonso	PH		15.08	120.94	65669
San Isidro	PE		-12.10	-77.04	68309
San Jacinto	US	California	33.78	-116.96	46951
San Joaquín	VE		10.26	-67.79	69894
San Jose	US	California	37.34	-121.89	997368
San Jose	PH		12.35	121.07	143495
San Jose del Monte	PH		14.81	121.05	357828
San Josecito	VE		7.66	-72.22	54669
San José	CR		9.93	-84.08	335007
San José de Guanipa	VE		8.89	-64.17	83092
San José de las Lajas	CU		22.96	-82.15	54847
San José del Cabo	MX		23.05	-109.70	136285
San José del Guaviare	CO		2.57	-72.64	52815
San José Pinula	GT		14.55	-90.41	79844
San Juan	PR		18.47	-66.11	418140
San Juan	PH		14.60	121.03	134312
San Juan	AR		-31.54	-68.53	109123
San Juan	PE		-3.78	-73.28	78153
San Juan	US	Texas	26.19	-98.16	36556
San Juan Bautista	VE		11.01	-63.94	90387
San Juan Capistrano	US	California	33.50	-117.66	36454
San Juan de la Maguana	DO		18.81	-71.23	72950
San Juan de los Morros	VE		9.91	-67.35	160868
San Juan del Río	MX		20.39	-100.00	138878
San Juan Sacatepéquez	GT		14.72	-90.64	136886
San Justo	AR		-34.68	-58.56	105274
San Leandro	US	California	37.72	-122.16	90712
San Leonardo	PH		15.36	120.96	69180
San Lorenzo	PY		-25.34	-57.51	227876
San Lorenzo	US	California	37.67	-122.13	23452
San Luis	AR		-33.29	-66.32	169947
San Luis	CU		20.19	-75.85	67293
San Luis	US	Arizona	32.49	-114.78	31520
San Luis Obispo	US	California	35.28	-120.66	47339
San Luis Potosí	MX		22.15	-100.97	722772
San Luis Río Colorado	MX		32.46	-114.77	176685
San Marcos	US	California	33.14	-117.17	92931
San Marcos	CO		8.66	-75.13	60735
San Marcos	US	Texas	29.88	-97.94	60684
San Marcos	SV		13.66	-89.18	54615
San Marino	SM		43.94	12.45	4500
San Martin	PE		-5.19	-80.67	130000
San Martin Texmelucan de Labastida	MX		19.28	-98.44	155738
San Martín	AR		-33.08	-68.47	82549
San Mateo	PH		14.70	121.12	134327
San Mateo	US	California	37.56	-122.33	103536
San Mateo	VE		10.21	-67.42	50401
San Mateo Atenco	MX		19.27	-99.53	67890
San Miguel	SV		13.48	-88.18	247126
San Miguel	AR		-34.54	-58.71	168762
San Miguel	PH		15.14	120.98	65661
San Miguel	PE		-15.48	-70.12	60850
San Miguel de Allende	MX		20.92	-100.74	174615
San Miguel de Tucumán	AR		-26.82	-65.21	548866
San Miguel del Padrón	CU		23.10	-82.33	159273
San Miguelito	PA		9.05	-79.47	321501
San Nicolás de los Arroyos	AR		-33.33	-60.21	134217
San Nicolás de los Garza	MX		25.74	-100.30	412199
San Pablo	PH		14.07	121.33	300166
San Pablo	US	California	37.96	-122.35	30407
San Pablo de las Salinas	MX		19.67	-99.09	156191
San Pedro	PH		14.36	121.05	348968
San Pedro	US	California	33.74	-118.29	83556
San Pedro Ayampuc	GT		14.78	-90.45	58609
San Pedro de Copán	HN		14.62	-88.87	63829
San Pedro de Jujuy	AR		-24.23	-64.87	58430
San Pedro de la Paz	CL		-36.84	-73.10	121631
San Pedro de Macorís	DO		18.45	-69.31	217899
San Pedro Garza García	MX		25.66	-100.40	132128
San Pedro Sula	HN		15.51	-88.03	801259
San Rafael	AR		-34.62	-68.33	118009
San Rafael	US	California	37.97	-122.53	59162
San Rafael	VE		10.96	-71.73	55810
San Ramon	US	California	37.78	-121.98	76134
San Ramón de la Nueva Orán	AR		-23.14	-64.32	86867
San Salvador	SV		13.69	-89.19	525990
San Salvador de Jujuy	AR		-24.19	-65.29	257970
San Salvador Tizatlalli	MX		19.26	-99.59	61367
San Sebastián de los Reyes	ES		40.56	-3.63	75912
San Severo	IT		41.69	15.38	51919
San Tan Valley	US	Arizona	33.19	-111.53	81321
San Timoteo	VE		9.79	-71.07	81017
San Tung Chung Hang	HK		22.28	113.94	116000
San Vicent del Raspeig	ES		38.40	-0.53	56715
San Vicente	AR		-35.02	-58.42	90021
San-Pédro	CI		4.75	-6.64	390654
Sanaa	YE		15.35	44.21	1937451
Sanandaj	IR		35.31	47.00	349176
Sancaktepe	TR		41.00	29.23	489848
Sanchazi	CN		42.08	126.60	66576
Sanchuan	CN		26.75	100.66	56345
Sancti Spíritus	CU		21.93	-79.44	127069
Sand Springs	US	Oklahoma	36.14	-96.11	19783
Sandachō	JP		34.88	135.23	132858
Sandakan	MY		5.84	118.12	439050
Sandalfoot Cove	US	Florida	26.34	-80.19	16582
Sandaohezi	CN		44.33	85.62	60129
Sandbach	GB		53.15	-2.36	17976
Sandefjord	NO		59.13	10.22	64345
Sandhurst	GB		51.35	-0.79	20803
Sandnes	NO		58.85	5.74	85386
Sandown	GB		50.65	-1.16	20155
Sandu	CN		19.79	109.22	76757
Sandusky	US	Ohio	41.45	-82.71	25212
Sandwīp	BD		22.51	91.45	52152
Sandy	US	Utah	40.59	-111.88	87461
Sandy Hills	US	Utah	40.58	-111.85	89575
Sandy Springs	US	Georgia	33.92	-84.38	105330
Sandyford	IE		53.27	-6.23	22288
Sandīla	IN		27.07	80.51	53182
Sanford	US	Florida	28.80	-81.27	58111
Sanford	US	North Carolina	35.48	-79.18	29144
Sanford	US	Maine	43.44	-70.77	20893
Sangamner	IN		19.57	74.21	67309
Sangarédi	GN		11.10	-13.77	54824
Sanger	US	California	36.71	-119.56	24950
Sanghar	PK		26.05	68.95	62033
Sangju	KR		36.42	128.16	101267
Sangkapura	ID		-5.85	112.65	50612
Sangla Hill	PK		31.72	73.38	103709
Sangmélima	CM		2.93	11.98	80036
Sangrūr	IN		30.25	75.84	88615
Sangyoung	MM		16.81	96.13	89618
Sangāreddi	IN		17.62	78.09	72344
Sanhe	CN		39.98	117.07	965075
Sanhe	CN		29.87	107.73	140954
Sanhui	CN		30.08	106.59	51413
Sanjō	JP		37.62	138.95	94642
Sankarankovil	IN		9.17	77.54	57277
Sankt Augustin	DE		50.78	7.20	56094
Sankt Gallen	CH		47.42	9.37	75833
Sanlúcar de Barrameda	ES		36.78	-6.35	68037
Sanmenxia	CN		34.78	111.19	669307
Sanming	CN		26.25	117.62	602166
Sano	JP		36.32	139.58	117669
Sanshui	CN		23.15	112.89	153714
Sant Andreu	ES		41.44	2.19	142598
Sant Boi de Llobregat	ES		41.34	2.04	82428
Sant Cugat del Vallès	ES		41.47	2.09	79253
Sant Martí	ES		41.42	2.20	235719
Sant'Ana do Livramento	BR		-30.89	-55.53	84421
Santa Ana	US	California	33.75	-117.87	310227
Santa Ana	SV		13.99	-89.56	176661
Santa Anita - Los Ficus	PE		-12.05	-76.97	184614
Santa Barbara	US	California	34.42	-119.70	91842
Santa Bárbara d'Oeste	BR		-22.75	-47.41	188000
Santa Catarina	MX		25.67	-100.46	304052
Santa Catarina Pinula	GT		14.57	-90.50	80582
Santa Cecilia	BR		-23.53	-46.65	80972
Santa Clara	CU		22.41	-79.97	250512
Santa Clara	US	California	37.35	-121.96	126215
Santa Clarita	US	California	34.39	-118.54	182371
Santa Coloma de Gramenet	ES		41.45	2.21	118821
Santa Cruz	PH		14.60	120.98	126735
Santa Cruz	PH		14.28	121.42	108145
Santa Cruz	PH		15.77	119.91	66647
Santa Cruz	US	California	36.97	-122.03	64220
Santa Cruz de Barahona	DO		18.21	-71.10	77160
Santa Cruz de la Sierra	BO		-17.79	-63.18	1831434
Santa Cruz de Mara	VE		10.79	-71.69	69781
Santa Cruz de Tenerife	ES		28.47	-16.25	211359
Santa Cruz de Yojoa	HN		14.98	-87.89	97848
Santa Cruz del Quiché	GT		15.03	-91.15	78279
Santa Cruz do Capibaribe	BR		-7.96	-36.20	98254
Santa Cruz do Sul	BR		-29.72	-52.43	133230
Santa Cruz Xoxocotlán	MX		17.03	-96.74	67086
Santa Fe	AR		-31.65	-60.71	391164
Santa Fe	US	New Mexico	35.69	-105.94	87505
Santa Fe Springs	US	California	33.95	-118.09	18026
Santa Inês	BR		-3.67	-45.38	85014
Santa Isabel	BR		-23.32	-46.22	53174
Santa Isabel do Pará	BR		-1.30	-48.16	73019
Santa Lucía	ES		27.91	-15.54	71863
Santa Lucía	AR		-31.54	-68.50	62697
Santa Lucía Cotzumalguapa	GT		14.34	-91.02	112780
Santa Luzia	BR		-19.77	-43.85	219132
Santa Luzia	BR		-3.96	-45.66	57635
Santa Maria	BR		-29.68	-53.81	271735
Santa Maria	BR		-16.03	-48.03	116622
Santa Maria	US	California	34.95	-120.44	105093
Santa Marta	CO		11.24	-74.19	499192
Santa María Chimalhuacán	MX		19.42	-98.95	70519
Santa Monica	US	California	34.02	-118.49	93220
Santa Paula	US	California	34.35	-119.06	30546
Santa Rita	BR		-7.11	-34.98	149910
Santa Rosa	PH		14.31	121.11	216650
Santa Rosa	US	California	38.44	-122.71	178127
Santa Rosa	AR		-36.62	-64.29	102860
Santa Rosa	BR		-27.87	-54.48	76963
Santa Rosa Beach	US	Florida	30.40	-86.23	32459
Santa Rosa de Cabal	CO		4.87	-75.62	57928
Santa Tecla	SV		13.68	-89.28	124694
Santa Teresa del Tuy	VE		10.23	-66.66	278890
Santana	BR		-23.49	-46.64	115689
Santana	BR		-0.04	-51.17	107618
Santana de Parnaíba	BR		-23.44	-46.92	154105
Santander	ES		43.47	-3.80	173635
Santander de Quilichao	CO		3.01	-76.48	99354
Santangpu	CN		27.41	111.99	58000
Santarém	BR		-2.44	-54.71	189047
Santee	US	California	32.84	-116.97	57787
Santiago	CL		-33.46	-70.65	4837295
Santiago	PH		16.69	121.55	108414
Santiago	PE		-13.53	-71.98	64075
Santiago de Compostela	ES		42.88	-8.55	99536
Santiago de Cuba	CU		20.02	-75.82	555865
Santiago de los Caballeros	DO		19.45	-70.69	1200000
Santiago de Querétaro	MX		20.59	-100.39	1594212
Santiago de Surco	PE		-12.14	-77.01	251648
Santiago del Estero	AR		-27.80	-64.26	252192
Santiago Teyahualco	MX		19.66	-99.12	53684
Santo Amaro	BR		-23.65	-46.70	85349
Santo Amaro	BR		-12.55	-38.71	56012
Santo André	BR		-23.66	-46.54	662373
Santo António	CN		22.20	113.54	129800
Santo Antônio de Jesus	BR		-12.97	-39.26	103055
Santo Antônio do Descoberto	BR		-15.94	-48.26	72127
Santo Domingo	DO		18.47	-69.89	2201941
Santo Domingo de los Colorados	EC		-0.25	-79.18	458580
Santo Domingo Este	DO		18.49	-69.85	700000
Santo Domingo Oeste	DO		18.50	-70.00	701269
Santo Domingo Tehuantepec	MX		16.32	-95.24	67739
Santo Estêvão	BR		-12.43	-39.25	52276
Santo Tomas	PH		14.11	121.14	57438
Santo Tomé	AR		-31.66	-60.77	59072
Santo Ângelo	BR		-28.30	-54.26	76917
Santol	PH		15.16	120.57	298976
Santos	BR		-23.96	-46.33	418608
Sants-Montjuïc	ES		41.37	2.15	183120
Santutxu	ES		43.25	-2.92	60000
Sanxia	TW		24.93	121.37	115185
Sanya	CN		18.25	109.51	1031396
Sanyōonoda	JP		34.03	131.16	60326
Sanzhuang	CN		35.50	119.17	52214
Sao Domingos	BR		-23.49	-46.75	88884
Sao Lucas	BR		-23.59	-46.54	138038
Sao Rafael	BR		-23.63	-46.45	148145
Sapele	NG		5.89	5.68	305000
Saphan Sung	TH		13.77	100.68	89825
Sapiranga	BR		-29.64	-51.01	75648
Sapopemba	BR		-23.60	-46.52	266715
Sapporo	JP		43.07	141.35	1973832
Sapucaia do Sul	BR		-29.82	-51.15	132107
Sapulpa	US	Oklahoma	36.00	-96.11	20579
Sapé	BR		-7.10	-35.23	51306
Saqqez	IR		36.25	46.27	165258
Saquarema	BR		-22.90	-42.47	95201
Sar-e Pul	AF		36.22	65.93	52121
Saraburi	TH		14.53	100.92	67763
Sarai Alamgir	PK		32.90	73.76	73967
Sarajevo	BA		43.85	18.36	696731
Sarandi	BR		-23.44	-51.87	118455
Sarandí	AR		-34.68	-58.35	60752
Saransk	RU		54.18	45.17	318841
Sarapul	RU		56.48	53.80	98830
Sarasota	US	Florida	27.34	-82.53	55118
Saratoga	US	California	37.26	-122.02	30968
Saratoga Springs	US	New York	43.08	-73.78	27765
Saratoga Springs	US	Utah	40.35	-111.90	25407
Saratov	RU		51.54	45.99	844858
Sarcelles	FR		49.00	2.38	57979
Sardārshahr	IN		28.44	74.49	95911
Sargodha	PK		32.09	72.67	975886
Sarh	TD		9.15	18.38	138928
Sari	IR		36.56	53.06	255396
Sarishābāri	BD		24.75	89.83	81325
Sariwŏn-si	KP		38.51	125.76	310100
Sarnia	CA		42.98	-82.40	72125
Sarov	RU		54.95	43.32	88000
Sarpsborg	NO		59.28	11.11	59038
Sarqant	KZ		45.41	79.92	76919
Sarrià-Sant Gervasi	ES		41.40	2.14	147912
Sartell	US	Minnesota	45.62	-94.21	16788
Sartrouville	FR		48.95	2.19	53980
Sarāvān	IR		27.37	62.33	60014
Sasarām	IN		24.95	84.02	147408
Sasebo	JP		33.17	129.73	243223
Saskatoon	CA		52.13	-106.67	266141
Sasolburg	ZA		-26.81	27.82	135828
Sassari	IT		40.73	8.56	91895
Satara	IN		17.69	73.99	120195
Sathon	TH		13.71	100.53	84916
Sathorn	TH		13.75	100.52	79624
Satna	IN		24.58	80.83	282977
Satpayev	KZ		47.90	67.54	69782
Sattahip	TH		12.67	100.90	65444
Satte	JP		36.07	139.73	55286
Sattenapalle	IN		16.39	80.15	56721
Satu Mare	RO		47.80	22.86	112490
Sau Mau Ping	HK		22.32	114.23	54218
Saugor	IN		23.84	78.74	274556
Saugus	US	Massachusetts	42.46	-71.01	26628
Sault Ste. Marie	CA		46.52	-84.33	72051
Saunda	IN		23.66	85.33	81915
Saurimo	AO		-9.66	20.39	393000
Savage	US	Minnesota	44.78	-93.34	30391
Savannah	US	Georgia	32.08	-81.10	147780
Savannakhet	LA		16.57	104.76	125760
Savar	BD		23.85	90.25	286008
Savarkundla	IN		21.34	71.30	78354
Savona	IT		44.31	8.48	61345
Sawai Madhopur	IN		26.02	76.34	121106
Sawangan	ID		-6.40	106.77	197170
Sawtelle	US	California	34.04	-118.45	39757
Sayama	JP		35.85	139.41	160843
Sayama	JP		34.52	135.56	58435
Sayhāt	SA		26.48	50.05	66702
Sayreville	US	New Jersey	40.46	-74.36	44920
Sayreville Junction	US	New Jersey	40.47	-74.33	42890
Sayville	US	New York	40.74	-73.08	16853
Sayyān	YE		15.17	44.32	69404
Saïda	DZ		34.83	0.15	142497
Scaggsville	US	Maryland	39.15	-76.90	24333
Scarborough	GB		54.28	-0.40	61749
Scarborough	AU		-31.90	115.76	17605
Scarborough Village	CA		43.74	-79.22	16724
Scarsdale	US	New York	41.01	-73.78	17885
Schaerbeek	BE		50.87	4.38	132761
Schaumburg	US	Illinois	42.03	-88.08	74693
Schenectady	US	New York	42.81	-73.94	65305
Schererville	US	Indiana	41.48	-87.45	28791
Schertz	US	Texas	29.55	-98.27	43091
Schiedam	NL		51.92	4.39	75438
Schofield Barracks	US	Hawaii	21.50	-158.07	16370
Schofield-Wheeler	US	Hawaii	21.48	-158.05	20452
Schweinfurt	DE		50.05	10.22	54012
Schweizer-Reneke	ZA		-27.19	25.33	70214
Schwerin	DE		53.63	11.41	96641
Schwerte	DE		51.44	7.57	50399
Schwäbisch Gmünd	DE		48.80	9.80	61216
Schöneberg	DE		52.50	13.34	122658
Scotch Plains	US	New Jersey	40.66	-74.39	23584
Scottsdale	US	Arizona	33.51	-111.90	236839
Scranton	US	Pennsylvania	41.41	-75.66	77118
Scunthorpe	GB		53.58	-0.65	81576
Seabrook	US	Maryland	38.97	-76.85	17287
Seafair	CA		49.15	-123.18	16070
Seaford	GB		50.77	0.10	22584
Seaford	AU		-38.10	145.13	17215
Seaford	US	New York	40.67	-73.49	15294
Seagoville	US	Texas	32.64	-96.54	15894
Seaham	GB		54.84	-1.35	22373
Seal Beach	US	California	33.74	-118.10	24619
Searcy	US	Arkansas	35.25	-91.74	24196
Seaside	US	California	36.61	-121.85	33025
SeaTac	US	Washington	47.45	-122.29	28215
Seattle	US	Washington	47.61	-122.33	780995
Sebastian	US	Florida	27.82	-80.47	24007
Sebeta	ET		8.92	38.62	102300
Secaucus	US	New Jersey	40.79	-74.06	19104
Secondigliano	IT		40.90	14.27	51874
Sector 1	RO		44.49	26.05	225453
Sector 2	RO		44.45	26.13	290507
Sector 3	RO		44.42	26.17	385439
Sector 4	RO		44.38	26.12	287828
Sector 5	RO		44.39	26.07	271575
Sector 6	RO		44.44	26.02	367760
Secunderabad	IN		17.50	78.54	204182
Security-Widefield	US	Colorado	38.75	-104.71	32882
Sedalia	US	Missouri	38.70	-93.23	21516
Seeb	OM		23.67	58.19	470878
Sefrou	MA		33.83	-4.83	87234
Segamat	MY		2.51	102.82	69816
Segovia	ES		40.95	-4.12	51683
Seguin	US	Texas	29.57	-97.96	27864
Sehore	IN		23.20	77.08	109118
Seinäjoki	FI		62.79	22.83	66848
Sejong	KR		36.59	127.29	394630
Sejoumi	TN		36.76	10.12	109672
Sekimachi	JP		35.48	136.92	85283
Sekondi	GH		4.93	-1.71	285506
Sekondi-Takoradi	GH		4.93	-1.76	138872
Sek’ot’a	ET		12.63	39.03	50300
Selayang Baru Utara	MY		3.25	101.67	542409
Selby	GB		53.78	-1.07	24859
Selden	US	New York	40.87	-73.04	19851
Selma	US	California	36.57	-119.61	24414
Selma	US	Alabama	32.41	-87.02	19519
Selong	ID		-8.65	116.53	92464
Selva Alegre	PE		-16.37	-71.53	72696
Semarang	ID		-6.99	110.42	1694740
Sembawang Estate	SG		1.45	103.83	110090
Semenyih	MY		2.95	101.84	92491
Semey	KZ		50.42	80.25	292780
Seminole	US	Florida	27.84	-82.79	18153
Semnan	IR		35.58	53.39	124826
Semporna	MY		4.48	118.61	62641
Semënovskoye	RU		55.68	37.55	50000
Senador Canedo	BR		-16.71	-49.09	118451
Sendai	JP		38.27	140.87	1096704
Sendai	JP		31.82	130.30	92403
Sendhwa	IN		21.69	75.10	56485
Sengerema	TZ		-2.67	32.65	110000
Sengkang	ID		-4.13	120.03	59523
Sengkang New Town	SG		1.39	103.89	267600
Senhor do Bonfim	BR		-10.46	-40.19	74523
Sennan	JP		34.35	135.27	60102
Sennar	SD		13.57	33.57	130122
Sentul	MY		3.18	101.68	100000
Seogwipo	KR		33.25	126.56	178552
Seongnam-si	KR		37.44	127.14	914832
Seoni	IN		22.09	79.55	102343
Seosan	KR		36.78	126.45	74208
Seoul	KR		37.57	126.98	10349312
Sepang	MY		2.69	101.75	212050
Sepatan	ID		-6.12	106.58	118439
Sept-Îles	CA		50.20	-66.38	28534
Seraing	BE		50.58	5.50	60737
Serang	ID		-6.12	106.15	735651
Serangoon	SG		1.36	103.90	116900
Serangoon New Town	SG		1.35	103.87	116900
Serekunda	GM		13.44	-16.68	340000
Seremban	MY		2.73	101.94	372917
Seremban 2	MY		2.69	101.91	62000
Serendah	MY		3.36	101.60	71202
Sergeli	UZ		41.20	69.22	105700
Sergiyev Posad	RU		56.31	38.14	109252
Seri Kembangan	MY		3.03	101.72	130252
Seri Manjung	MY		4.20	100.67	100000
Serian	MY		1.17	110.57	58059
Serilingampalle	IN		17.49	78.30	150525
Seropédica	BR		-22.74	-43.71	84737
Serov	RU		59.60	60.59	98438
Serowe	BW		-22.39	26.71	55676
Serpong	ID		-6.32	106.66	80193
Serpukhov	RU		54.92	37.42	128158
Serra	BR		-20.13	-40.31	520653
Serra Talhada	BR		-7.99	-38.30	86915
Serrinha	BR		-11.66	-39.01	80435
Sertãozinho	BR		-21.14	-47.99	126887
Sesto San Giovanni	IT		45.53	9.23	81822
Sesvete	HR		45.83	16.12	55313
Set Ka Lay	MM		16.81	96.11	111514
Setagaya	JP		35.64	139.65	940071
Setapak	MY		3.21	101.73	353268
Setauket-East Setauket	US	New York	40.93	-73.10	15477
Sete Lagoas	BR		-19.47	-44.25	227397
Setia Alam	MY		3.10	101.46	150000
Setia Tropika	MY		1.55	103.72	60279
Seto	JP		35.23	137.10	127792
Settat	MA		33.00	-7.62	155333
Settsu	JP		34.78	135.60	87456
Setúbal	PT		38.52	-8.89	118166
Sevastopol	UA		44.61	33.52	547820
Seven Hills	AU		-33.78	150.93	19196
Seven Oaks	US	South Carolina	34.05	-81.15	15144
Seven Sisters	GB		51.58	-0.08	15968
Sevenoaks	GB		51.27	0.19	29506
Severn	US	Maryland	39.14	-76.70	44231
Severna Park	US	Maryland	39.07	-76.55	37634
Severnyy	RU		55.94	37.55	200000
Severodvinsk	RU		64.56	39.83	194292
Severomorsk	RU		69.07	33.41	53921
Seversk	RU		56.60	84.89	109844
Sevierville	US	Tennessee	35.87	-83.56	16490
Sevilla	ES		37.38	-5.97	686741
Sewell	US	New Jersey	39.77	-75.14	37433
Sewon	ID		-7.88	110.36	73585
Seydişehir	TR		37.42	31.85	51089
Seymour	US	Indiana	38.96	-85.89	19478
Seymour	US	Connecticut	41.40	-73.08	16562
Sfax	TN		34.74	10.76	280566
Sfântu Gheorghe	RO		45.87	25.78	50080
Sha Tin	HK		22.38	114.18	495200
Sha Tin Wai	HK		22.38	114.20	80000
Shabqadar	PK		34.22	71.55	102340
Shache	CN		38.42	77.24	128145
Shadrinsk	RU		56.09	63.64	79479
Shadwell	GB		51.51	-0.06	15110
Shafter	US	California	35.50	-119.27	18336
Shagamu	NG		6.85	3.65	214558
Shah Alam	MY		3.09	101.53	740750
Shahdad Kot	PK		27.85	67.91	120687
Shahdadpur	PK		25.93	68.62	113342
Shahdol	IN		23.29	81.36	89289
Shahecheng	CN		36.94	114.51	125132
Shahkot	PK		31.57	73.49	244868
Shahr-e Bābak	IR		30.12	55.12	51620
Shahr-e Kord	IR		32.33	50.86	129153
Shahr-e Ṣadrā	IR		29.80	52.50	122226
Shahrak-e Pardīsān	IR		34.56	50.80	100000
Shahre Jadide Andisheh	IR		35.68	51.02	116062
Shahreẕā	IR		32.01	51.86	134952
Shahrisabz	UZ		39.06	66.83	142700
Shahrixon	UZ		40.71	72.06	71400
Shahrud	IR		36.42	54.98	165000
Shahrīār	IR		35.66	51.06	309607
Shahuwadi	IN		16.91	73.95	180322
Shajing	CN		22.75	113.82	127089
Shajing Town	CN		22.74	113.81	67093
Shakargarh	PK		32.26	75.16	126742
Shaker Heights	US	Ohio	41.47	-81.54	27646
Shakhtarsk	UA		48.06	38.44	71700
Shakhty	RU		47.72	40.22	221312
Shakopee	US	Minnesota	44.80	-93.53	39981
Sham Shui Po	HK		22.33	114.16	431090
Shancheng	CN		34.80	116.08	74459
Shanghai	CN		31.22	121.46	24874500
Shangkou	CN		36.97	118.88	65770
Shangluo	CN		33.87	109.93	531696
Shangmei	CN		27.74	111.30	75233
Shangqiu	CN		34.41	115.66	1859723
Shangrao	CN		28.45	117.94	1116486
Shangri-La	CN		27.83	99.71	186400
Shangsi	CN		22.16	107.98	71468
Shangyu	CN		30.02	120.87	770000
Shangzhi	CN		45.21	128.00	131006
Shanhaiguan	CN		40.00	119.75	140000
Shanhecun	CN		45.71	128.58	57550
Shanji	CN		34.20	117.60	50617
Shankou	CN		21.60	109.72	70153
Shanting	CN		35.08	117.46	80843
Shantou	CN		23.35	116.68	3838900
Shanwang	CN		36.55	118.71	63195
Shanwei	CN		22.78	115.35	491766
Shaoguan	CN		24.80	113.58	1028460
Shaoshan	CN		27.92	112.52	118000
Shaowu	CN		27.34	117.48	112585
Shaoxing	CN		30.00	120.58	2300000
Shaoyang	CN		27.24	111.46	753194
Shaozhuang	CN		36.75	118.32	66728
Shap Pat Heung	HK		22.42	114.04	77775
Shaping	CN		22.77	112.96	107589
Sharifabad	PK		33.43	73.36	55027
Sharjah	AE		25.33	55.41	1800000
Shashamane	ET		7.20	38.60	208400
Shaw	US	District of Columbia	38.91	-77.02	17639
Shawinigan	CA		46.57	-72.75	38211
Shawnee	US	Kansas	39.04	-94.72	65046
Shawnee	US	Oklahoma	35.33	-96.93	31286
Shchukino	RU		55.80	37.45	102000
Shchyolkovo	RU		55.92	37.97	113000
Shchëkino	RU		54.01	37.51	60700
Sheboygan	US	Wisconsin	43.75	-87.71	48797
Sheepshead Bay	US	New York	40.59	-73.94	122534
Sheffield	GB		53.38	-1.47	556500
Shegaon	IN		20.79	76.70	59672
Sheikhpura	IN		25.14	85.84	62927
Shekhupura	PK		31.71	73.99	591424
Sheki	AZ		41.19	47.17	68400
Shelby	US	Michigan	42.67	-83.03	74099
Shelby	US	North Carolina	35.29	-81.54	20189
Shelbyville	US	Tennessee	35.48	-86.46	21317
Shelbyville	US	Indiana	39.52	-85.78	19133
Shelbyville	US	Kentucky	38.21	-85.22	15253
Shella	IN		25.18	91.64	54039
Shelton	US	Connecticut	41.32	-73.09	41296
Shenandoah	US	Louisiana	30.40	-91.00	18399
Shendi	SD		16.69	33.43	63746
Shengavit	AM		40.16	44.48	140600
Shenglilu	CN		29.35	105.88	134218
Shenjiamen	CN		29.96	122.30	95433
Shenliu	CN		29.41	112.16	57769
Shenyang	CN		41.79	123.43	7050000
Shenzhen	CN		22.55	114.07	17494398
Shenzhen City Centre	CN		22.54	114.08	70826
Sheopur	IN		25.66	76.70	71951
Shepherds Bush	GB		51.51	-0.22	39724
Shepparton	AU		-36.38	145.40	32067
Sheptytskyi	UA		50.39	24.24	64297
Sherbrooke	CA		45.40	-71.90	129447
Sheridan	US	Wyoming	44.80	-106.96	17873
Sherkot	IN		29.33	78.57	57361
Sherman	US	Texas	33.64	-96.61	40667
Sherman Oaks	US	California	34.15	-118.45	52677
Sherpur	BD		25.02	90.02	107419
Sherrelwood	US	Colorado	39.84	-105.00	18287
Sherwood	US	Arkansas	34.82	-92.22	30517
Sherwood	US	Oregon	45.36	-122.84	19283
Sherwood Park	CA		53.52	-113.32	70618
Shevchenkivskyi	UA		50.46	30.47	220077
Shevchenkivskyi	UA		48.56	39.33	87516
Shevchenko	UA		49.56	34.54	147600
Shibata	JP		37.95	139.33	96236
Shibganj	BD		25.00	89.32	378701
Shibirghān	AF		36.67	65.75	55641
Shibukawa	JP		36.48	139.00	76098
Shibuya	JP		35.66	139.71	230609
Shibuzi	CN		36.12	119.10	58333
Shibīn al Kawm	EG		30.55	31.01	267945
Shibīn al Qanāţir	EG		30.31	31.32	73711
Shiguai	CN		40.71	110.29	70357
Shihezi	CN		44.30	86.04	572772
Shijiazhuang	CN		38.04	114.48	3938513
Shijie	CN		23.10	113.79	246960
Shijōnawate	JP		34.73	135.68	55177
Shikang	CN		21.77	109.32	64818
Shikarpur	PK		27.96	68.64	204938
Shiki	JP		35.83	139.58	76445
Shikohābād	IN		27.11	78.59	99678
Shikokuchūō	JP		33.98	133.55	82754
Shilin	CN		24.82	103.33	55000
Shillong	IN		25.57	91.88	143229
Shilong	CN		23.11	113.85	109733
Shima	CN		28.99	105.92	69881
Shima	CN		24.45	117.81	68375
Shimada	JP		34.82	138.18	95719
Shimla	IN		31.10	77.17	173503
Shimodate	JP		36.30	139.98	63666
Shimonoseki	JP		33.96	130.94	265684
Shimotoda	JP		35.81	139.69	140899
Shimotsuke	JP		36.41	139.87	60274
Shinagawa	JP		33.64	133.01	422488
Shinjuku	JP		35.69	139.71	349385
Shinyanga	TZ		-3.66	33.42	139727
Shiogama	JP		38.32	141.03	52662
Shiojiri	JP		36.10	137.97	67241
Shipley	GB		53.83	-1.77	28544
Shiqi	CN		22.52	113.39	342306
Shiqiao	CN		22.95	113.36	135308
Shiqiaozi	CN		36.16	119.26	58538
Shiquan	CN		33.04	108.24	53422
Shirakawa	JP		37.12	140.26	59491
Shiraoka	JP		36.02	139.66	52214
Shiraz	IR		29.61	52.53	1249942
Shirbīn	EG		31.20	31.52	76081
Shirley	GB		52.41	-1.82	32000
Shirley	US	New York	40.80	-72.87	27854
Shiroi	JP		35.80	140.07	62441
Shirpur	IN		21.35	74.88	76905
Shitanjing	CN		39.23	106.34	78765
Shivaji Nagar	IN		18.53	73.85	1000000
Shivamogga	IN		13.93	75.57	322650
Shively	US	Kentucky	38.20	-85.82	15713
Shivpuri	IN		25.42	77.66	179977
Shiwan	CN		23.00	113.08	82031
Shixing	CN		24.95	114.07	72996
Shiyan	CN		32.65	110.78	3460000
Shizhai	CN		34.81	116.64	62956
Shizilu	CN		35.17	118.83	86749
Shizuishan	CN		38.98	106.39	739400
Shizuoka	JP		34.98	138.38	693389
Shkodër	AL		42.07	19.51	95553
Sholapur	IN		17.67	75.91	997281
Shomolu	NG		6.54	3.37	154390
Shoreham-by-Sea	GB		50.83	-0.27	19175
Shoreline	US	Washington	47.76	-122.34	55439
Shoreview	US	Minnesota	45.08	-93.15	26477
Shorewood	US	Illinois	41.52	-88.20	16747
Shorkot	PK		31.91	70.88	67439
Short Pump	US	Virginia	37.65	-77.61	24729
Shorāpur	IN		16.52	76.76	51398
Shostka	UA		51.86	33.47	73197
Shouguang	CN		36.88	118.74	473620
Shouxian	CN		34.85	116.46	76030
Shreveport	US	Louisiana	32.53	-93.75	187593
Shrewsbury	GB		52.71	-2.75	76782
Shrewsbury	US	Massachusetts	42.30	-71.71	33893
Shrirampur	IN		19.62	74.66	89282
Shrīrāmpur	IN		22.75	88.34	226317
Shuangcheng	CN		45.38	126.31	130710
Shuangfengqiao	CN		29.72	106.63	67717
Shuangliao	CN		43.51	123.50	93666
Shuanglonghu	CN		29.72	106.61	128563
Shuangyang	CN		43.52	125.66	62137
Shuangyashan	CN		46.68	131.13	600000
Shubrā al Khaymah	EG		30.13	31.25	1240289
Shuifu	CN		28.63	104.41	102143
Shuijiang	CN		29.25	107.28	50918
Shuikou	CN		23.98	115.90	62321
Shuizhai	CN		23.93	115.76	140493
Shujaabad	PK		29.88	71.29	151115
Shujālpur	IN		23.41	76.71	51225
Shulan	CN		44.41	126.95	77420
Shulin	TW		24.99	121.42	180044
Shulyavka	UA		50.45	30.45	62200
Shumen	BG		43.27	26.92	72342
Shunyi	CN		40.12	116.65	117623
Shuozhou	CN		39.32	112.42	433700
Shuya	RU		56.85	41.39	60705
Shwebo	MM		22.57	95.70	88914
Shwegu	MM		24.23	96.79	58696
Shyamnagar	IN		22.83	88.37	441956
Shymkent	KZ		42.31	69.60	1200000
Shāhjānpur	IN		27.88	79.91	320434
Shāhpur	IN		16.70	76.84	53366
Shāhzādpur	BD		24.18	89.60	102420
Shāhābād	IN		27.64	79.94	73606
Shāhābād	IN		17.13	76.94	52952
Shāhāda	IN		21.55	74.47	61376
Shāhīn Shahr	IR		32.86	51.55	173329
Shājāpur	IN		23.43	76.28	69263
Shāmli	IN		29.45	77.31	97966
Shāntipur	IN		23.25	88.43	149983
Shīrvān	IR		37.40	57.93	82790
Shūnan	JP		34.08	131.83	149632
Shūsh	IR		32.19	48.24	77148
Shūshtar	IR		32.05	48.85	101878
Si Maha Phot	TH		13.97	101.51	100563
Si Racha	TH		13.17	100.93	178916
Sialkot	PK		32.49	74.53	911817
Sibay	RU		52.72	58.67	61590
Sibi	PK		29.54	67.88	64069
Sibiu	RO		45.80	24.15	134309
Sibolga	ID		1.74	98.78	92244
Sibonga	PH		10.02	123.62	54610
Sibsāgar	IN		26.98	94.64	62104
Sibu	MY		2.30	111.82	198239
Sicklerville	US	New Jersey	39.72	-74.97	42891
Siddhapur	IN		23.92	72.37	61867
Siddharthanagar	NP		27.50	83.45	63367
Siddipet	IN		18.10	78.85	66737
Sidhi	IN		24.40	81.88	54331
Sidi Aïssa	DZ		35.89	3.77	66856
Sidi Bel Abbes	DZ		35.19	-0.63	210146
Sidi Bennour	MA		32.65	-8.43	60948
Sidi Kacem	MA		34.22	-5.71	82632
Sidi Slimane	MA		34.26	-5.93	101541
Sidi Taibi	MA		34.19	-6.68	51050
Sidikalang	ID		2.75	98.31	50671
Sidlaghatta	IN		13.39	77.86	51159
Sidney	US	Ohio	40.28	-84.16	20858
Sidoarjo	ID		-7.45	112.72	139189
Sidon	LB		33.56	35.37	163554
Siedlce	PL		52.17	22.29	77185
Siegen	DE		50.87	8.02	107242
Siem Reap	KH		13.36	103.86	139458
Siemianowice Śląskie	PL		50.33	19.03	73121
Siena	IT		43.32	11.33	53901
Sierra Vista	US	Arizona	31.55	-110.30	43355
Sig	DZ		35.53	-0.19	61373
Siguatepeque	HN		14.60	-87.83	127468
Siguiri	GN		11.42	-9.17	148018
Sihanoukville	KH		10.61	103.53	73036
Siheungdong	KR		37.45	126.91	128142
Sihor	IN		21.71	71.96	54547
Siirt	TR		37.93	41.94	114034
Sikandarābād	IN		28.45	77.70	73379
Sikasso	ML		11.32	-5.67	349324
Sikeston	US	Missouri	36.88	-89.59	16436
Silang	PH		14.22	120.97	119475
Silao de la Victoria	MX		20.94	-101.43	74242
Silchar	IN		24.83	92.80	178865
Silifke	TR		36.38	33.93	132665
Siliguri	IN		26.71	88.43	515574
Silivri	TR		41.07	28.25	53167
Sillod	IN		20.30	75.65	58230
Siloam Springs	US	Arkansas	36.19	-94.54	16081
Silopi	TR		37.24	42.46	114645
Silvan	TR		38.14	41.01	65956
Silvassa	IN		20.27	73.00	98265
Silver Firs	US	Washington	47.87	-122.16	20891
Silver Lake	US	California	34.09	-118.27	32890
Silver Spring	US	Maryland	38.99	-77.03	71452
Silverdale	US	Washington	47.64	-122.69	19204
Simele	IQ		36.86	42.85	152512
Simferopol	UA		44.96	34.11	336460
Simi Valley	US	California	34.27	-118.78	126788
Simmering	AT		48.18	16.43	101420
Simpang Empat	MY		4.95	100.63	58004
Simpang Renggam	MY		1.82	103.31	59033
Simpsonville	US	South Carolina	34.74	-82.25	20736
Simões Filho	BR		-12.78	-38.40	114559
Sinan	KR		34.83	126.11	53150
Sincelejo	CO		9.30	-75.39	277773
Sinch’ŏn-ŭp	KP		38.35	125.48	141407
Sindelfingen	DE		48.70	9.02	61311
Sindhnūr	IN		15.77	76.76	75837
Sinfin	GB		52.88	-1.49	15128
Sinfra	CI		6.62	-5.91	245226
Singa	SD		13.15	33.93	250000
Singapore	SG		1.29	103.85	5638700
Singaraja	ID		-8.11	115.09	133784
Singida	TZ		-4.82	34.74	232459
Singkawang	ID		0.91	108.98	253812
Singosari	ID		-7.89	112.67	182656
Singrauli	IN		24.20	82.68	220257
Sinhyeon	KR		34.88	128.63	82560
Sinjhoro	PK		26.03	68.81	354709
Sinnar	IN		19.85	74.00	65299
Sinnūris	EG		29.41	30.87	133532
Sinop	BR		-11.86	-55.50	216029
Sinp’o	KP		40.04	128.19	152759
Sint-Niklaas	BE		51.17	4.14	69010
Sintang	ID		0.07	111.50	85000
Sinwŏn-ŭp	KP		38.24	125.76	83161
Sinŭiju	KP		40.10	124.40	288112
Siocon	PH		7.71	122.14	51239
Sioux City	US	Iowa	42.50	-96.40	82821
Sioux Falls	US	South Dakota	43.54	-96.73	171544
Sipalay	PH		9.75	122.40	73847
Siping	CN		43.16	124.38	555609
Siracusa	IT		37.08	15.29	121605
Sirajganj	BD		24.46	89.71	127481
Sirhind	IN		30.64	76.38	60847
Sirjan	IR		29.45	55.68	199704
Sironj	IN		24.10	77.69	52460
Sirs al Layyānah	EG		30.44	30.97	78168
Sirsa	IN		29.53	75.03	182534
Sirsi	IN		14.62	74.84	62882
Sirsilla	IN		18.39	78.81	83186
Sirte	LY		31.21	16.59	106705
Siruguppa	IN		15.63	76.89	52492
Sishui	CN		35.65	117.28	90175
Sitiawan	MY		4.22	100.70	156234
Sitou	CN		36.31	118.41	56289
Sitrah	BH		26.15	50.62	72601
Sittingbourne	GB		51.34	0.73	54392
Sittwe	MM		20.15	92.90	177743
Situbondo	ID		-7.71	114.01	685967
Siu Lek Yuen	HK		22.38	114.21	57349
Siuri	IN		23.91	87.53	64659
Sivakasi	IN		9.45	77.80	234704
Sivas	TR		39.75	37.02	264022
Siverek	TR		37.76	39.32	175341
Siverskodonetsk	UA		48.94	38.49	99067
Siwān	IN		26.22	84.36	135066
Skanes	TN		35.77	10.79	64222
Skardu	PK		35.30	75.63	260000
Skegness	GB		53.14	0.34	24876
Skelmersdale	GB		53.55	-2.77	38813
Skhidni Kvartaly	UA		48.57	39.38	102500
Skhirate	MA		33.85	-7.03	65272
Skien	NO		59.21	9.61	50595
Skikda	DZ		36.88	6.91	182903
Skokie	US	Illinois	42.03	-87.73	64821
Skopje	MK		42.00	21.43	474889
Skudai	MY		1.54	103.66	159733
Slatina	RO		44.43	24.37	63487
Slavyansk-na-Kubani	RU		45.25	38.12	65196
Slawi	ID		-6.98	109.14	61206
Sleaford	GB		53.00	-0.41	17359
Sleman	ID		-7.72	110.36	56215
Slidell	US	Louisiana	30.28	-89.78	27942
Sligo	IE		54.27	-8.47	20608
Sliven	BG		42.69	26.33	83740
Slough	GB		51.51	-0.60	164793
Slovyansk	UA		48.85	37.60	105141
Slutsk	BY		53.02	27.54	58995
Smederevo	RS		44.66	20.93	62000
Smethwick	GB		52.49	-1.97	53653
Smila	UA		49.23	31.88	66475
Smithfield	US	Rhode Island	41.92	-71.55	21872
Smithtown	US	New York	40.86	-73.20	26470
Smolensk	RU		54.78	32.05	330025
Smolyanskyi	UA		48.01	37.74	116779
Smyrna	US	Georgia	33.88	-84.51	56146
Smyrna	US	Tennessee	35.98	-86.52	46607
Snellville	US	Georgia	33.86	-84.02	19733
Snezhinsk	RU		56.08	60.75	50086
Snizhne	UA		48.02	38.76	55587
Snowdon	CA		45.49	-73.63	32160
Soacha	CO		4.58	-74.22	655025
Sobradinho	BR		-15.65	-47.79	72273
Sobradinho II	BR		-15.63	-47.83	82785
Sobral	BR		-3.69	-40.35	203023
Socastee	US	South Carolina	33.68	-79.00	19952
Sochi	RU		43.60	39.72	327608
Socopó	VE		8.23	-70.82	72352
Socorro	US	Texas	31.65	-106.30	33222
Socorro Mission Number 1 Colonia	US	Texas	31.64	-106.29	28637
Sodegaura	JP		35.41	140.02	64901
Sodo	ET		6.86	37.76	204100
Sofia	BG		42.70	23.32	1152556
Sogamoso	CO		5.71	-72.93	111336
Sohag	EG		26.56	31.69	266944
Sohar	OM		24.35	56.71	108274
Soho	GB		51.51	-0.14	19634
Sokaraja	ID		-7.46	109.29	66482
Sokcho	KR		38.21	128.59	81164
Sokhumi	GE		43.01	40.99	65439
Sokodé	TG		8.98	1.13	117811
Sokol	RU		55.80	37.52	57000
Sokol’niki	RU		55.80	37.67	57000
Sokoto	NG		13.06	5.24	1040000
Solana	PH		17.65	121.69	71475
Soledad	CO		10.92	-74.76	342556
Soledad	US	California	36.42	-121.33	25003
Soledad de Graciano Sánchez	MX		22.19	-100.94	332072
Soligorsk	BY		52.79	27.54	96418
Solihull	GB		52.41	-1.78	126577
Solikamsk	RU		59.67	56.74	100812
Solingen	DE		51.17	7.08	164359
Sollentuna	SE		59.43	17.95	139606
Solna	SE		59.36	18.00	66909
Solnechnogorsk	RU		56.18	36.97	58891
Solntsevo	RU		55.64	37.38	120000
Solok	ID		-0.80	100.66	73438
Solon	US	Ohio	41.39	-81.44	23043
Solwezi	ZM		-12.17	26.39	301370
Soma	TR		39.19	27.61	98714
Somaroboro	ZA		-25.35	28.83	114369
Somerset	US	New Jersey	40.50	-74.49	22083
Somerset	US	Massachusetts	41.77	-71.13	18165
Somerset West	ZA		-34.08	18.82	225289
Somerton	US	Pennsylvania	40.12	-75.01	33247
Somerton	US	Arizona	32.60	-114.71	15048
Somerville	US	Massachusetts	42.39	-71.10	80318
Songcheng	CN		26.88	120.00	165730
Songea	TZ		-10.68	35.65	286285
Songjiang	CN		31.03	121.22	1973500
Songjianghe	CN		42.19	127.48	67672
Songkhla	TH		7.20	100.60	61758
Songling	CN		31.19	120.72	77566
Songlingcun	CN		40.29	118.27	52277
Songlou	CN		34.57	116.60	79763
Songnan	CN		31.35	121.48	127347
Songnim-ni	KP		38.76	125.64	152425
Songyang	CN		34.46	113.03	62375
Songyuan	CN		45.13	124.83	113611
Sonsonate	SV		13.72	-89.72	59468
Sonārgaon	BD		23.65	90.62	130000
Sonīpat	IN		28.99	77.02	289333
Sooke	CA		48.37	-123.73	15086
Sopron	HU		47.69	16.59	62246
Sopur	IN		34.29	74.47	71292
Soran	IQ		36.66	44.54	91589
Soreang	ID		-7.03	107.52	116780
Sorel-Tracy	CA		46.04	-73.11	41629
Sorgun	TR		39.81	35.19	62862
Sorocaba	BR		-23.50	-47.46	762172
Sorong	ID		-0.88	131.26	219958
Soroti	UG		1.71	33.61	60900
Sorriso	BR		-12.55	-55.71	120985
Sorsogon	PH		12.97	123.99	187670
Soshanguve	ZA		-25.47	28.10	872309
Sosnovka	RU		60.02	30.35	66227
Sosnovyy Bor	RU		59.90	29.09	68563
Sosnowiec	PL		50.29	19.10	227295
Sotsmisto	UA		48.74	37.59	53370
Soubré	CI		5.78	-6.59	131181
Sougueur	DZ		35.19	1.50	71036
Souk Ahras	DZ		36.29	7.95	153479
Souk El Arbaa	MA		34.68	-6.00	75635
Souq Sebt Oulad Nemma	MA		32.30	-6.70	65601
Sousa	BR		-6.76	-38.23	67259
Sousse	TN		35.83	10.64	221715
South Bel Air	US	Maryland	39.53	-76.34	48828
South Bend	US	Indiana	41.68	-86.25	101516
South Benfleet	GB		51.55	0.56	48824
South Boston	US	Massachusetts	42.33	-71.05	571281
South Bradenton	US	Florida	27.46	-82.58	22178
South Burlington	US	Vermont	44.47	-73.17	18791
South Chicago	US	Illinois	41.74	-87.55	28095
South Croydon	GB		51.36	-0.09	55198
South Dublin	IE		53.29	-6.34	301075
South El Monte	US	California	34.05	-118.05	20878
South Elgin	US	Illinois	41.99	-88.29	22365
South Elmsall	GB		53.60	-1.28	18835
South Euclid	US	Ohio	41.52	-81.52	21794
South Fulton	US	Georgia	33.59	-84.67	107436
South Gate	US	California	33.95	-118.21	96401
South Gate	US	Maryland	39.13	-76.63	29658
South Granville	CA		49.26	-123.14	24820
South Hadley	US	Massachusetts	42.26	-72.57	17652
South Hayling	GB		50.79	-0.98	15485
South Hill	US	Washington	47.14	-122.27	52431
South Holland	US	Illinois	41.60	-87.61	22043
South Houston	US	Texas	29.66	-95.24	17544
South Jordan	US	Utah	40.56	-111.93	66648
South Jordan Heights	US	Utah	40.56	-111.95	37141
South Kingstown	US	Rhode Island	41.45	-71.52	30826
South Lake Tahoe	US	California	38.93	-119.98	21706
South Laurel	US	Maryland	39.07	-76.85	26112
South Lawndale	US	Illinois	41.84	-87.71	73826
South Miami Heights	US	Florida	25.60	-80.38	36770
South Milwaukee	US	Wisconsin	42.91	-87.86	21233
South Morang	AU		-37.65	145.10	24989
South Norwood	GB		51.40	-0.07	16518
South Ockendon	GB		51.51	0.28	22440
South Ogden	US	Utah	41.19	-111.97	16955
South Old Bridge	US	New Jersey	40.41	-74.35	23233
South Orange	US	New Jersey	40.75	-74.26	17295
South Ozone Park	US	New York	40.67	-73.82	75878
South Parkdale	CA		43.64	-79.44	21849
South Pasadena	US	California	34.12	-118.15	26151
South Peabody	US	Massachusetts	42.51	-70.95	50293
South Plainfield	US	New Jersey	40.58	-74.41	24290
South Portland	US	Maine	43.64	-70.24	25556
South Portland Gardens	US	Maine	43.64	-70.32	23893
South Riding	US	Virginia	38.92	-77.50	24256
South River	US	New Jersey	40.45	-74.39	16399
South Riverdale	CA		43.65	-79.34	27876
South Ruislip	GB		51.56	-0.41	16800
South Saint Paul	US	Minnesota	44.89	-93.03	20160
South Salt Lake	US	Utah	40.72	-111.89	24788
South San Francisco	US	California	37.65	-122.41	67271
South San Jose Hills	US	California	34.01	-117.90	20551
South Shields	GB		55.00	-1.43	83655
South Shore	US	Illinois	41.76	-87.58	51451
South Suffolk	US	Virginia	36.72	-76.59	80690
South Surrey	CA		49.05	-122.79	77170
South Tangerang	ID		-6.29	106.72	1429529
South Valley	US	New Mexico	35.01	-106.68	40976
South Vineland	US	New Jersey	39.45	-75.03	58122
South Whittier	US	California	33.95	-118.04	57156
South Windsor	US	Connecticut	41.82	-72.62	24412
South Yarra	AU		-37.84	144.99	25237
South Yuba City	US	California	39.12	-121.64	15217
Southall	GB		51.51	-0.37	78253
Southampton	GB		50.90	-1.40	269781
Southaven	US	Mississippi	34.99	-90.01	52589
Southbank	AU		-37.82	144.96	22631
Southbridge	US	Massachusetts	42.08	-72.03	19030
Southbury	US	Connecticut	41.48	-73.21	19836
Southchase	US	Florida	28.39	-81.38	15921
Southend-on-Sea	GB		51.54	0.71	295310
Southfield	US	Michigan	42.47	-83.22	73156
Southgate	US	Michigan	42.21	-83.19	29293
Southglenn	US	Colorado	39.59	-104.95	42268
Southington	US	Connecticut	41.60	-72.88	43501
Southlake	US	Texas	32.94	-97.13	29941
Southport	GB		53.65	-3.01	91703
Southport	AU		-27.97	153.40	32965
Southsea	GB		50.78	-1.09	18514
Southwest Waterfront	US	District of Columbia	38.88	-77.02	15129
Soweto	ZA		-26.27	27.86	1695047
Soyapango	SV		13.71	-89.14	329708
Soyo	AO		-6.13	12.37	221555
Soyībug	IN		34.08	74.71	104000
Spalding	GB		52.79	-0.15	30556
Spanaway	US	Washington	47.10	-122.43	27227
Spanish Fork	US	Utah	40.11	-111.65	37935
Spanish Lake	US	Missouri	38.79	-90.22	19650
Spanish Springs	US	Nevada	39.65	-119.71	15064
Spanish Town	JM		17.99	-76.96	145018
Sparks	US	Nevada	39.53	-119.75	96094
Sparta	US	New Jersey	41.03	-74.64	19722
Spartanburg	US	South Carolina	34.95	-81.93	37867
Speke	GB		53.34	-2.84	21403
Spennymoor	GB		54.70	-1.60	17766
Speyer	DE		49.32	8.43	50343
Spijkenisse	NL		51.84	4.33	74988
Split	HR		43.51	16.44	149830
Spokane	US	Washington	47.66	-117.43	229447
Spokane Valley	US	Washington	47.67	-117.24	94919
Spring	US	Texas	30.08	-95.42	54298
Spring Hill	US	Florida	28.48	-82.53	98621
Spring Hill	US	Tennessee	35.75	-86.93	36055
Spring Valley	US	Nevada	36.11	-115.25	178395
Spring Valley	US	New York	41.11	-74.04	32598
Spring Valley	US	California	32.74	-117.00	28205
Springboro	US	Ohio	39.55	-84.23	18213
Springdale	US	Arkansas	36.19	-94.13	77859
Springfield	US	Missouri	37.22	-93.30	170188
Springfield	US	Massachusetts	42.10	-72.59	154341
Springfield	US	Illinois	39.80	-89.64	114394
Springfield	US	Oregon	44.05	-123.02	60870
Springfield	US	Ohio	39.92	-83.81	59680
Springfield	US	Virginia	38.79	-77.19	30484
Springfield	US	Pennsylvania	39.93	-75.32	23363
Springfield	US	Tennessee	36.51	-86.89	16808
Springfield Gardens	US	New York	40.66	-73.76	30515
Springfield Lakes	AU		-27.67	152.92	15081
Springs	ZA		-26.25	28.40	186394
Springvale	AU		-37.95	145.15	22174
Springville	US	Utah	40.17	-111.61	32286
Spruce Grove	CA		53.53	-113.92	38985
Squamish	CA		49.70	-123.16	23819
Sragen	ID		-7.43	111.02	71522
Sri Dūngargarh	IN		28.10	74.01	53294
Sri Ganganagar	IN		29.92	73.87	237780
Sri Jayewardenepura Kotte	LK		6.88	79.91	115826
Sri Petaling	MY		3.07	101.69	50000
Srikakulam	IN		18.30	83.90	137944
Srikalahasti	IN		13.76	79.70	80056
Srinagar	IN		34.09	74.81	1206419
Srivilliputhur	IN		9.51	77.63	75396
St Albans	GB		51.75	-0.33	84561
St Albans	AU		-37.74	144.80	37629
St Austell	GB		50.34	-4.77	24360
St Clair	AU		-33.80	150.78	19856
St Helens	GB		53.45	-2.73	183200
St. Albert	CA		53.63	-113.64	57719
St. Andrew-Windfields	CA		43.76	-79.38	17812
St. Catharines	CA		43.17	-79.24	136803
St. Charles	US	Maryland	38.61	-76.92	33379
St. Charles	US	Illinois	41.91	-88.31	32974
St. James-Assiniboia East	CA		49.89	-97.23	27755
St. John's	CA		47.56	-52.71	110525
St. Johns	US	Florida	30.08	-81.55	40000
St. Louis	US	Missouri	38.63	-90.20	279695
St. Marys	US	Georgia	30.73	-81.55	17968
St. Petersburg	US	Florida	27.77	-82.68	257083
St. Thomas	CA		42.77	-81.18	38909
Stafford	GB		52.81	-2.12	70145
Stafford	US	Texas	29.62	-95.56	18459
Staines	GB		51.43	-0.51	51040
Stallings	US	North Carolina	35.09	-80.69	15270
Stalowa Wola	PL		50.58	22.05	66495
Stalybridge	GB		53.48	-2.06	26830
Stamford	US	Connecticut	41.05	-73.54	128874
Stamford	GB		52.65	-0.48	20592
Stamford Hill	GB		51.57	-0.07	68050
Standerton	ZA		-26.93	29.24	101101
Stanford-le-Hope	GB		51.52	0.43	29525
Stanley	GB		54.87	-1.70	31300
Stanley	FK		-51.69	-57.86	2213
Stanton	US	California	33.80	-117.99	38872
Stara Zagora	BG		42.43	25.64	121582
Starachowice	PL		51.04	21.07	53739
Stargard	PL		53.34	15.05	71224
Starkville	US	Mississippi	33.45	-88.82	25366
Staryy Oskol	RU		51.30	37.85	226977
State College	US	Pennsylvania	40.79	-77.86	42161
Staten Island	US	New York	40.56	-74.14	468730
Statesboro	US	Georgia	32.45	-81.78	30721
Statesville	US	North Carolina	35.78	-80.89	26221
Staunton	US	Virginia	38.15	-79.07	24416
Stavanger	NO		58.97	5.73	151669
Staveley	GB		53.27	-1.35	25719
Stavropol	RU		45.03	41.96	433931
Steeles	CA		43.81	-79.33	24623
Steglitz	DE		52.46	13.33	72464
Steinbach	CA		49.53	-96.68	15829
Stellenbosch	ZA		-33.93	18.87	96228
Stephenville	US	Texas	32.22	-98.20	20120
Stepney	GB		51.52	-0.04	16238
Sterling	US	Virginia	39.01	-77.43	27822
Sterling	US	Illinois	41.79	-89.70	15057
Sterling Heights	US	Michigan	42.58	-83.03	132052
Sterlitamak	RU		53.64	55.95	267231
Steubenville	US	Ohio	40.37	-80.63	18219
Stevenage	GB		51.90	-0.20	91774
Stevens Point	US	Wisconsin	44.52	-89.57	26604
Stevenson Ranch	US	California	34.39	-118.57	17557
Steveston	CA		49.13	-123.18	25220
Stilfontein	ZA		-26.84	26.77	93110
Stillwater	US	Oklahoma	36.12	-97.06	48967
Stillwater	US	Minnesota	45.06	-92.81	18924
Stirling	GB		56.12	-3.94	37910
Stittsville	CA		45.25	-75.92	40889
Stockbridge	US	Georgia	33.54	-84.23	28202
Stockholm	SE		59.33	18.07	1515017
Stockport	GB		53.41	-2.16	139052
Stockton	US	California	37.96	-121.29	305658
Stockton-on-Tees	GB		54.57	-1.32	79957
Stodůlky	CZ		50.05	14.32	60758
Stoke	NZ		-41.32	173.23	20260
Stoke-on-Trent	GB		53.00	-2.19	258366
Stolberg	DE		50.77	6.23	57684
Stonebridge	CA		52.08	-106.62	16392
Stonecrest	US	Georgia	33.71	-84.13	50000
Stonegate	US	California	33.71	-117.74	18938
Stonegate-Queensway	CA		43.64	-79.50	25051
Stoneham	US	Massachusetts	42.48	-71.10	21437
Stoney Creek	CA		43.22	-79.77	76382
Stony Plain	CA		53.53	-114.00	17993
Storrs	US	Connecticut	41.81	-72.25	15344
Stouffville	CA		43.97	-79.25	36753
Stoughton	US	Massachusetts	42.13	-71.10	26915
Stourbridge	GB		52.46	-2.14	56950
Stourport-on-Severn	GB		52.34	-2.28	20586
Stow	US	Ohio	41.16	-81.44	34797
Stowmarket	GB		52.19	1.00	21028
Stralsund	DE		54.31	13.08	58976
Strasbourg	FR		48.58	7.75	274845
Stratford	US	Connecticut	41.18	-73.13	51384
Stratford	GB		51.53	0.00	36666
Stratford	CA		43.37	-80.95	31465
Stratford-upon-Avon	GB		52.19	-1.71	30495
Strathfield	AU		-33.88	151.08	25769
Strathroy	CA		42.96	-81.62	23871
Strawberry Hill	CA		49.13	-122.88	41000
Strawberry Mansion	US	Pennsylvania	39.98	-75.18	15778
Streamwood	US	Illinois	42.03	-88.18	40554
Streatham	GB		51.43	-0.13	58055
Streetsboro	US	Ohio	41.24	-81.35	16312
Stretford	GB		53.45	-2.32	41953
Strogino	RU		55.82	37.41	152000
Strongsville	US	Ohio	41.31	-81.84	44668
Strood	GB		51.39	0.48	33381
Stroud	GB		51.75	-2.20	60155
Stryi	UA		49.26	23.85	61404
Stróvolos	CY		35.15	33.33	67904
Stuart	US	Florida	27.20	-80.25	16462
Studio City	US	California	34.15	-118.40	34034
Stupino	RU		54.90	38.07	60999
Stuttgart	DE		48.78	9.18	612663
Suan Luang	TH		13.73	100.65	115658
Subang	ID		-6.57	107.76	137234
Subang Jaya	MY		3.04	101.58	708296
Subic	PH		14.88	120.23	67664
Subotica	RS		46.10	19.67	100000
Subulussalam	ID		2.66	97.88	105553
Suceava	RO		47.63	26.25	84308
Sucre	BO		-19.03	-65.26	224838
Sudbury	GB		52.04	0.73	23912
Sudbury	US	Massachusetts	42.38	-71.42	17343
Sudley	US	Virginia	38.79	-77.50	16203
Suez	EG		29.97	32.53	699541
Suffolk	US	Virginia	36.73	-76.58	88161
Sugar Hill	US	Georgia	34.11	-84.03	21747
Sugar Land	US	Texas	29.62	-95.63	88156
Suginami	JP		36.20	140.28	588354
Suhum	GH		6.04	-0.45	50610
Suicheng	CN		33.90	117.93	256665
Suifenhe	CN		44.40	131.15	98561
Suihua	CN		46.65	126.97	252245
Suiling	CN		47.23	127.11	57124
Suining	CN		30.51	105.57	656760
Suisun	US	California	38.24	-122.04	28111
Suita	JP		34.76	135.52	385567
Suitland	US	Maryland	38.85	-76.92	25825
Suitland-Silver Hill	US	Maryland	38.85	-76.93	33515
Suixi	CN		33.89	116.77	74172
Suizhou	CN		31.71	113.36	618582
Sujiatun	CN		41.66	123.34	148113
Sukabumi	ID		-6.92	106.93	365735
Sukagawa	JP		37.28	140.38	74992
Sukawati	ID		-8.49	115.05	125470
Sukkur	PK		27.70	68.86	563851
Sukrah	TN		36.88	10.25	159862
Sukuta	GM		13.41	-16.71	56472
Sulaymaniyah	IQ		35.56	45.43	878146
Suleja	NG		9.18	7.18	162135
Sullana	PE		-4.90	-80.69	160789
Sulphur	US	Louisiana	30.24	-93.38	20189
Sulphur Springs	US	Texas	33.14	-95.60	16098
Sultan Kudarat	PH		7.23	124.26	124965
Sultan Pur Majra	IN		28.69	77.08	181554
Sultanbeyli	TR		40.96	29.27	358201
Sultangazi	TR		41.11	28.87	436935
Sultānganj	IN		25.24	86.74	52892
Sultānpur	IN		26.26	82.07	110368
Sulţānah	SA		24.49	39.59	946697
Sumaré	BR		-22.82	-47.27	279545
Sumayl	IQ		36.86	42.85	152512
Sumbawa Besar	ID		-8.49	117.42	62753
Sumbawanga	TZ		-7.97	31.62	303986
Sumbe	AO		-11.21	13.84	205832
Sumber	ID		-6.76	108.48	96725
Sumedang	ID		-6.86	107.92	200000
Sumedang Utara	ID		-6.85	107.92	100000
Sumenep	ID		-7.01	113.86	84656
Sumgayit	AZ		40.59	49.67	427000
Sumida	JP		35.73	139.82	287766
Summerlin South	US	Nevada	36.12	-115.33	24085
Summerville	US	South Carolina	33.02	-80.18	48848
Summit	US	New Jersey	40.72	-74.36	22074
Sumter	US	South Carolina	33.92	-80.34	40816
Sumusţā al Waqf	EG		28.92	30.85	64965
Sumy	UA		50.92	34.80	256474
Sun City	US	Arizona	33.60	-112.27	37499
Sun City	US	California	33.71	-117.20	19579
Sun City Center	US	Florida	27.72	-82.35	19258
Sun City West	US	Arizona	33.66	-112.34	24535
Sun Prairie	US	Wisconsin	43.18	-89.21	32365
Sun Valley	US	Nevada	39.60	-119.78	19299
Sunabeda	IN		18.73	82.83	50394
Sunbury	AU		-37.58	144.73	38851
Sunbury-on-Thames	GB		51.40	-0.42	27784
Suncheon	KR		34.95	127.49	276375
Sunch’ŏn	KP		39.43	125.93	437000
Sunderland	GB		54.90	-1.38	170134
Sundsvall	SE		62.39	17.31	57606
Sungai Buloh	MY		3.21	101.56	222858
Sungai Penuh	ID		-2.06	101.39	102224
Sungai Petani	MY		5.65	100.49	544851
Sungailiat	ID		-1.85	106.12	100750
Sunggal	ID		3.58	98.62	157914
Sunland	US	California	34.27	-118.30	15316
Sunland Park	US	New Mexico	31.80	-106.58	15940
Sunny Isles Beach	US	Florida	25.95	-80.12	22123
Sunnybank Hills	AU		-27.61	153.05	17842
Sunnyside	US	New York	40.74	-73.94	49833
Sunnyside	US	Washington	46.32	-120.01	16325
Sunnyvale	US	California	37.37	-122.04	155805
Sunrise	US	Florida	26.13	-80.11	84439
Sunrise Manor	US	Nevada	36.21	-115.07	189372
Sunset	CA		49.22	-123.10	36500
Sunset	US	Florida	25.71	-80.35	16389
Sunset Park	US	New York	40.65	-74.01	126000
Sunshine Coast	AU		-26.66	153.08	398840
Sunshine West	AU		-37.79	144.82	18552
Sunyani	GH		7.34	-2.33	92825
Sunzha	RU		43.32	45.05	71841
Sunām	IN		30.13	75.80	69069
Sunāmganj	BD		25.07	91.40	74570
Suozhen	CN		36.95	118.10	58766
Supaul	IN		26.12	86.60	65437
Superior	US	Wisconsin	46.72	-92.10	26579
Suphan Buri	TH		14.47	100.12	53399
Suqian	CN		33.95	118.30	1437685
Sur	OM		22.57	59.53	71152
Surabaya	ID		-7.25	112.75	3018022
Surakarta	ID		-7.56	110.83	526870
Surallah	PH		6.38	124.75	91412
Surat	IN		21.20	72.83	4591246
Surat Thani	TH		9.14	99.33	132040
Suratgarh	IN		29.32	73.90	70536
Surbiton	GB		51.39	-0.30	38158
Surendranagar	IN		22.73	71.65	179628
Surfers Paradise	AU		-28.00	153.43	31073
Surgut	RU		61.26	73.42	300367
Surigao	PH		9.79	125.50	87832
Suriāpet	IN		17.14	79.62	111729
Surprise	US	Arizona	33.63	-112.33	143148
Surrey	CA		49.11	-122.83	568322
Surrey City Centre	CA		49.19	-122.85	33520
Surry Hills	AU		-33.88	151.21	15828
Surubim	BR		-7.83	-35.75	64120
Surulere	NG		6.50	3.36	191920
Suruç	TR		36.98	38.43	101178
Susanville	US	California	40.42	-120.65	15247
Susono	JP		35.17	138.91	51216
Sutton	GB		51.35	-0.20	187600
Sutton Coldfield	GB		52.57	-1.82	109899
Sutton in Ashfield	GB		53.13	-1.26	36404
Suva	FJ		-18.14	178.43	77366
Suva Reka	XK		42.36	20.82	72229
Suwanee	US	Georgia	34.05	-84.07	18694
Suwałki	PL		54.11	22.93	69222
Suwon	KR		37.29	127.01	1234582
Suyangshan	CN		34.39	117.76	65333
Suzaka	JP		36.65	138.32	54022
Suzano	BR		-23.54	-46.31	307429
Suzhou	CN		31.30	120.60	6715559
Suzhou	CN		33.64	116.98	1647642
Suzuka	JP		34.88	136.58	195670
Svetlanovskiy	RU		60.00	30.33	85508
Svetlogorsk	BY		52.63	29.74	61812
Sviblovo	RU		55.85	37.63	60000
Svobodnyy	RU		51.37	128.14	61017
Svyatoshyn	UA		50.46	30.35	53000
Swabi	PK		34.12	72.47	97363
Swadlincote	GB		52.77	-1.56	34576
Swakopmund	NA		-22.68	14.53	53009
Swanley	GB		51.40	0.17	21839
Swanscombe	GB		51.45	0.31	15801
Swansea	GB		51.62	-3.94	300352
Swansea	US	Massachusetts	41.75	-71.19	16525
Swedru	GH		5.54	-0.70	54417
Sweetwater	US	Florida	25.76	-80.37	20840
Swift Current	CA		50.28	-107.80	16604
Swindon	GB		51.56	-1.78	201669
Swinton	GB		53.50	-2.35	22931
Swords	IE		53.46	-6.22	40776
Sycamore	US	Illinois	41.99	-88.69	17712
Sydney	AU		-33.87	151.21	5638830
Sydney	CA		46.14	-60.18	105968
Sydney Central Business District	AU		-33.86	151.21	25654
Sykhiv	UA		49.79	24.06	151131
Syktyvkar	RU		61.66	50.82	245083
Sylhet	BD		24.90	91.87	237000
Sylmar	US	California	34.31	-118.45	79614
Sylvan Lake	CA		52.31	-114.08	17477
Sylvania	US	Ohio	41.72	-83.71	18965
Syosset	US	New York	40.83	-73.50	18829
Syracuse	US	New York	43.05	-76.15	144142
Syracuse	US	Utah	41.09	-112.06	27395
Syzran	RU		53.16	48.47	189338
Szczecin	PL		53.43	14.55	395513
Szeged	HU		46.25	20.15	160766
Szolnok	HU		47.18	20.20	71285
Szombathely	HU		47.23	16.62	78025
Székesfehérvár	HU		47.19	18.41	101600
São Bento do Sul	BR		-26.25	-49.38	83277
São Bernardo do Campo	BR		-23.69	-46.56	743372
São Borja	BR		-28.66	-56.00	60019
São Caetano do Sul	BR		-23.62	-46.55	165655
São Carlos	BR		-22.02	-47.89	205035
São Cristóvão	BR		-11.01	-37.21	95612
São Francisco	BR		-15.95	-44.86	52762
São Francisco do Sul	BR		-26.24	-48.64	52674
São Félix do Xingu	BR		-6.64	-51.99	65418
São Gabriel	BR		-30.34	-54.32	58487
São Gabriel da Cachoeira	BR		-0.12	-67.09	56406
São Gonçalo do Amarante	BR		-5.79	-35.33	115838
São Gonçalo do Amarante	BR		-3.61	-38.97	54143
São José	BR		-27.62	-48.63	270299
São José	BR		-28.21	-49.16	200000
São José de Ribamar	BR		-2.56	-44.06	244579
São José do Rio Pardo	BR		-21.60	-46.89	52205
São José do Rio Preto	BR		-20.82	-49.38	480393
São José dos Campos	BR		-23.18	-45.89	727078
São José dos Pinhais	BR		-25.53	-49.21	329628
São João da Boa Vista	BR		-21.97	-46.80	92547
São João de Meriti	BR		-22.80	-43.37	466536
São João del Rei	BR		-21.14	-44.26	78592
São Leopoldo	BR		-29.76	-51.15	209229
São Lourenço	CN		22.19	113.53	51700
São Lourenço da Mata	BR		-8.00	-35.02	111249
São Luís	BR		-2.53	-44.30	917237
São Mateus	BR		-23.61	-46.48	155682
São Mateus	BR		-18.72	-39.86	123752
São Miguel	BR		-23.49	-46.43	81011
São Miguel do Guamá	BR		-1.63	-47.48	52894
São Miguel dos Campos	BR		-9.78	-36.09	53391
São Paulo	BR		-23.55	-46.64	12400232
São Pedro da Aldeia	BR		-22.84	-42.10	110556
São Roque	BR		-23.53	-47.14	79484
São Sebastião	BR		-15.90	-47.78	98612
São Sebastião	BR		-23.76	-45.41	81595
São Sebastião do Paraíso	BR		-20.92	-46.99	71796
São Tomé	ST		0.34	6.73	53300
São Vicente	BR		-23.96	-46.39	329911
Sé	MO		22.19	113.55	52200
Ségou	ML		13.44	-6.26	205787
Séguéla	CI		7.96	-6.67	103980
Sérres	GR		41.08	23.55	58287
Sétif	DZ		36.19	5.41	252127
Sóc Sơn	VN		21.26	105.85	85431
Sóc Trăng	VN		9.60	105.97	221430
Sông Cầu	VN		13.46	109.22	94066
Södermalm	SE		59.31	18.08	127323
Södertälje	SE		59.20	17.63	70777
Söke	TR		37.75	27.41	68230
Sādatpur Gujran	IN		28.73	77.25	97641
Sāgar	IN		14.16	75.03	54550
Sāhibganj	IN		25.24	87.63	95890
Sāhibābād Daulotpur	IN		28.75	77.11	54773
Sālūr	IN		18.52	83.21	50206
Sāmalkot	IN		17.06	82.18	56864
Sāmarrā’	IQ		34.20	43.89	158508
Sānand	IN		22.99	72.38	95890
Sāngli	IN		16.85	74.56	601214
Sārni	IN		22.10	78.17	86141
Sātkania	BD		22.08	92.05	52005
Sātkhira	BD		22.71	89.07	128918
Sāveh	IR		35.02	50.36	220762
Sīkar	IN		27.61	75.14	244497
Sīnah	IQ		36.81	43.04	128776
Sīra	IN		13.74	76.90	57928
Sītāmarhi	IN		26.59	85.49	67818
Sītāpur	IN		27.56	80.68	164435
Słupsk	PL		54.46	17.03	98608
Sōja	JP		34.68	133.75	69030
Sōka	JP		35.84	139.80	249645
Sūjāngarh	IN		27.70	74.47	183808
Sūsangerd	IR		31.56	48.19	51431
Sơn La	VN		21.33	103.92	106052
Sơn Trà	VN		16.06	108.23	86890
Sơn Tây	VN		21.14	105.51	230577
Sầm Sơn	VN		19.73	105.90	129801
Ta Khmau	KH		11.48	104.95	52066
Tabaco	PH		13.36	123.73	57860
Tabatinga	BR		-4.23	-69.94	72283
Tabora	TZ		-5.02	32.83	308741
Taboão da Serra	BR		-23.63	-46.79	273542
Tabriz	IR		38.08	46.29	1424641
Tabuk	SA		28.40	36.57	667000
Tabuk	PH		17.47	121.47	122771
Tabuk	PH		17.41	121.28	122771
Tacarigua	VE		10.09	-67.92	69636
Tacheng	CN		46.75	82.96	161037
Tachikawa	JP		35.71	139.42	183581
Tachilek	MM		20.45	99.88	51553
Tacloban	PH		11.24	125.00	259353
Tacna	PE		-18.01	-70.25	286240
Tacoma	US	Washington	47.25	-122.44	222906
Tacony	US	Pennsylvania	40.03	-75.04	17846
Tacuarembó	UY		-31.72	-55.98	60586
Tacurong	PH		6.69	124.68	116945
Tadepalligudem	IN		16.81	81.53	112655
Tadley	GB		51.35	-1.13	15836
Tadmur	SY		34.56	38.28	51015
Tadpatri	IN		14.91	78.01	108171
Tafo	GH		6.73	-1.61	50457
Tagajō-shi	JP		38.30	141.00	62827
Taganrog	RU		47.24	38.91	279056
Taganskiy	RU		55.73	37.67	116000
Tagawa	JP		33.63	130.80	51608
Tagaytay	PH		14.10	120.93	87811
Tagbilaran City	PH		9.66	123.85	86411
Taguatinga	BR		-15.83	-48.06	193367
Taguig	PH		14.52	121.08	1308085
Tahara	JP		34.67	137.27	60206
Tahe	CN		52.32	124.70	60874
Tahlequah	US	Oklahoma	35.92	-94.97	16598
Tahoua	NE		14.89	5.27	159468
Tai Po	HK		22.45	114.17	274100
Taibai	CN		30.82	108.36	108387
Taicang	CN		31.45	121.09	831113
Taichung	TW		24.15	120.68	2850285
Taifu	CN		28.98	105.64	58663
Taihe	CN		30.10	106.05	66506
Taikkyi	MM		17.31	95.96	88000
Tailai	CN		46.39	123.41	66623
Tailândia	BR		-2.95	-48.95	72493
Tainan	TW		22.99	120.21	1856642
Taipa	MO		22.16	113.56	112051
Taipei	TW		25.05	121.53	7871900
Taiping	MY		4.85	100.73	217647
Taishan	CN		22.25	112.78	145440
Taito	JP		35.71	139.78	211444
Taitou	CN		37.03	118.63	60354
Taitung	TW		22.76	121.14	103260
Taixing	CN		32.17	120.01	79655
Taiyuan	CN		37.87	112.56	4303673
Taiz	YE		13.58	44.02	940600
Taizhou	CN		32.49	119.91	1607108
Taizhou	CN		28.66	121.43	1485502
Tai’an	CN		36.19	117.12	1735425
Taj Pul	IN		28.49	77.31	68796
Tajimi	JP		35.32	137.13	107818
Tajrīsh	IR		35.80	51.43	86000
Takaishi	JP		34.52	135.43	60511
Takamatsu	JP		34.33	134.05	418994
Takanini	NZ		-37.04	174.93	17060
Takaoka	JP		36.75	137.02	170077
Takarazuka	JP		34.80	135.36	226432
Takasago	JP		34.76	134.79	87722
Takasaki	JP		36.33	139.02	372973
Takatsuki	JP		34.85	135.62	354468
Takayama	JP		36.13	137.25	88473
Takefu	JP		35.90	136.17	75753
Takeo	KH		10.99	104.78	843931
Takizawa	JP		39.80	141.13	55579
Takoma Park	US	Maryland	38.98	-77.01	17713
Takoradi	GH		4.90	-1.76	389114
Takāb	IR		36.40	47.11	51541
Talagang	PK		32.93	72.42	79431
Talagante	CL		-33.66	-70.93	57323
Talara	PE		-4.58	-81.27	99074
Talatona	AO		-8.92	13.19	500000
Talavera	PH		15.59	120.92	64610
Talavera de la Reina	ES		39.96	-4.83	88856
Talca	CL		-35.42	-71.65	197479
Talcahuano	CL		-36.72	-73.12	150499
Taldykorgan	KZ		45.02	78.37	116558
Talegaon Dābhāde	IN		18.74	73.68	56435
Talhar	PK		24.88	68.81	200014
Taling Chan	TH		13.78	100.46	105299
Taliparamba	IN		12.04	75.36	72465
Talisay	PH		10.24	123.85	133148
Talisay	PH		10.74	122.97	109204
Taliwang	ID		-8.74	116.85	55340
Talladega	US	Alabama	33.44	-86.11	15709
Tallaght	IE		53.29	-6.37	81022
Tallahassee	US	Florida	30.44	-84.28	201731
Tallang-dong	KR		33.49	126.48	54954
Tallinn	EE		59.44	24.75	394024
Tallmadge	US	Ohio	41.10	-81.44	17512
Talnakh	RU		69.49	88.40	59051
Taloqan	AF		36.74	69.53	64256
Talā	EG		30.68	30.94	72536
Tam Kỳ	VN		15.57	108.47	165240
Tam O'Shanter-Sullivan	CA		43.78	-79.30	27446
Tama	JP		35.64	139.47	148285
Tamale	GH		9.40	-0.84	464316
Taman Melati	MY		3.22	101.72	50000
Taman Melawati	MY		3.21	101.75	99304
Taman Petaling	MY		3.20	101.65	423062
Taman Senai	MY		1.60	103.64	73176
Taman Senawang Indah	MY		2.69	101.99	64497
Tamana	JP		32.95	130.57	64292
Tamanghasset	DZ		22.79	5.52	81752
Tamano	JP		34.52	133.95	67786
Tamarac	US	Florida	26.21	-80.25	64681
Tamba	JP		35.17	135.03	61471
Tambacounda	SN		13.77	-13.67	149071
Tambaram	IN		12.92	80.13	174787
Tambov	RU		52.74	41.44	293661
Tamiami	US	Florida	25.76	-80.40	55271
Tampa	US	Florida	27.95	-82.46	414547
Tampere	FI		61.50	23.79	260646
Tampico	MX		22.29	-97.88	309003
Tampines Estate	SG		1.36	103.94	265340
Tampines New Town	SG		1.35	103.95	259900
Tamworth	GB		52.63	-1.70	81964
Tamworth	AU		-31.09	150.93	43874
Tan-Tan	MA		28.44	-11.10	79942
Tanabe	JP		33.73	135.37	70972
Tanabe	JP		34.82	135.77	65903
Tanashichō	JP		35.73	139.54	82112
Tanauan	PH		14.09	121.15	68456
Tanay	PH		14.50	121.28	59950
Tanba	JP		35.16	135.04	62152
Tandil	AR		-37.33	-59.14	115877
Tando Adam	PK		25.77	68.66	174291
Tando Allahyar	PK		25.46	68.72	421923
Tando Bago	PK		24.79	68.97	426535
Tando Jam	PK		25.43	68.53	71760
Tando Muhammad Khan	PK		25.12	68.54	114406
Tandur	IN		17.25	77.58	65115
Tanfang	CN		36.70	118.67	91460
Tanga	TZ		-5.07	39.10	393429
Tangail	BD		24.25	89.92	180144
Tangará da Serra	BR		-14.62	-57.49	112547
Tangerang	ID		-6.18	106.63	1927815
Tanggu	CN		39.02	117.65	535298
Tanghe	CN		32.69	112.83	278055
Tangier	MA		35.77	-5.80	1035141
Tangjiazhuang	CN		39.74	118.45	79489
Tangping	CN		22.03	111.94	81729
Tangshan	CN		39.64	118.18	3372102
Tangwu	CN		36.45	118.86	93260
Tangxiang	CN		29.70	105.72	66325
Tangzhai	CN		34.43	116.59	67936
Tangzhang	CN		34.15	117.25	52985
Tanjay	PH		9.52	123.16	84593
Tanjong Malim	MY		3.68	101.52	66103
Tanjung Pandan	ID		-2.73	107.63	103062
Tanjung Pinang	ID		0.92	104.46	227663
Tanjung Selor	ID		2.84	117.37	67837
Tanjungagung	ID		-3.94	103.80	53117
Tanjungbalai	ID		2.97	99.80	190935
Tanque Verde	US	Arizona	32.25	-110.74	16901
Tanta	EG		30.79	31.00	576648
Tantou	CN		22.75	113.83	320304
Tantou	CN		26.03	119.60	69050
Tanuku	IN		16.75	81.68	77962
Tanza	PH		14.68	120.94	105510
Tanzhou	CN		22.26	113.47	382445
Taoluo	CN		35.27	119.37	61852
Taonan	CN		45.33	122.78	112819
Taourirt	MA		34.41	-2.90	112908
Taoyuan	TW		24.99	121.30	475798
Taoyuan	CN		33.85	117.77	52861
Taozhou	CN		30.91	119.41	146610
Taozhuang	CN		34.85	117.33	60137
Tapachula	MX		14.91	-92.26	353706
Taquara	BR		-29.65	-50.78	53242
Taquaritinga	BR		-21.41	-48.50	52260
Taradale	CA		51.12	-113.94	17630
Tarakan	ID		3.31	117.59	255310
Taranto	IT		40.46	17.25	198585
Tarawa	KI		1.33	172.98	40311
Taraz	KZ		42.90	71.37	358153
Tarbes	FR		43.23	0.07	52106
Taree	AU		-31.91	152.45	16359
Targówek	PL		52.29	21.05	124279
Tarhuna	LY		32.44	13.63	52420
Tarija	BO		-21.54	-64.73	159269
Tarime	TZ		-1.35	34.37	133043
Tarlac City	PH		15.48	120.60	401892
Tarma	PE		-11.42	-75.69	51350
Tarn Taran	IN		31.45	74.93	66847
Tarneit	AU		-37.84	144.66	56370
Tarnobrzeg	PL		50.57	21.68	50459
Tarnowskie Góry	PL		50.45	18.86	60938
Tarnów	PL		50.01	20.99	117799
Taroudant	MA		30.47	-8.88	87520
Tarpon Springs	US	Florida	28.15	-82.76	24605
Tarragona	ES		41.12	1.25	141542
Tarsus	TR		36.92	34.89	350732
Tartagal	AR		-22.52	-63.81	60819
Tartu	EE		58.38	26.73	91407
Tarub	ID		-6.93	109.17	75739
Tasek Glugor	MY		5.48	100.50	135786
Tashan	CN		34.34	117.57	59162
Tashkent	UZ		41.26	69.22	1978028
Tasikmalaya	ID		-7.33	108.22	770839
Tatabánya	HU		47.59	18.38	65849
Tataouine	TN		32.93	10.45	66924
Tatebayashi	JP		36.25	139.53	81274
Tateyama	JP		34.98	139.87	50064
Tatsuno	JP		34.83	134.54	74316
Tatuapé	BR		-23.54	-46.57	98601
Tatuí	BR		-23.36	-47.86	129130
Tatvan	TR		38.49	42.28	73222
Taubaté	BR		-23.03	-45.56	322397
Taungdwingyi	MM		20.01	95.55	70094
Taunggyi	MM		20.79	97.04	160115
Taungoo	MM		18.94	96.43	106945
Taunsa	PK		30.70	70.65	115704
Taunton	GB		51.01	-3.10	64621
Taunton	US	Massachusetts	41.90	-71.09	56789
Taupo	NZ		-38.68	176.08	27000
Tauranga	NZ		-37.69	176.17	161000
Tauá	BR		-6.00	-40.29	61227
Tavares	US	Florida	28.80	-81.73	15430
Tavşanlı	TR		39.54	29.50	52182
Tawau	MY		4.24	117.89	372615
Taxco de Alarcón	MX		18.55	-99.61	50399
Tayabas	PH		14.03	121.59	115318
Taylor	US	Michigan	42.24	-83.27	61568
Taylor	US	Texas	30.57	-97.41	16702
Taylor-Massey	CA		43.70	-79.30	15683
Taylors	US	South Carolina	34.92	-82.30	21617
Taylors Hill	AU		-37.71	144.75	15419
Taylors Lakes	AU		-37.70	144.79	15174
Taylorsville	US	Utah	40.67	-111.94	60514
Taytay	PH		14.56	121.13	231460
Taza	MA		34.21	-4.01	162110
Ta’if	SA		21.27	40.42	688693
Tbilisi	GE		41.69	44.83	1049498
Tczew	PL		54.09	18.78	60133
Te Atatu Peninsula	NZ		-36.84	174.65	15200
Te Atatu South	NZ		-36.86	174.65	17240
Teaneck	US	New Jersey	40.90	-74.02	40078
Tebingtinggi	ID		3.33	99.16	117530
Tecate	MX		32.57	-116.63	64764
Techiman	GH		7.59	-1.94	84074
Tecomán	MX		18.92	-103.88	85689
Tecumseh	CA		42.32	-82.88	23229
Tefé	BR		-3.37	-64.72	79278
Tegal	ID		-6.87	109.14	297173
Teghra	IN		25.49	85.94	56234
Tegucigalpa	HN		14.08	-87.21	850848
Tehran	IR		35.69	51.42	7153309
Tehuacán	MX		18.46	-97.40	248716
Teixeira de Freitas	BR		-17.54	-39.74	145216
Tejen	TM		37.38	60.51	67488
Tekirdağ	TR		40.98	27.51	122287
Tekstil’shchiki	RU		55.70	37.74	100000
Tekstylnyk	UA		47.95	37.70	75000
Tel Aviv	IL		32.08	34.78	432892
Telde	ES		27.99	-15.42	123265
Telford	GB		52.68	-2.45	155570
Tellicherry	IN		11.75	75.49	97201
Teluk Intan	MY		4.02	101.02	232800
Teluknaga	ID		-6.10	106.64	175155
Telêmaco Borba	BR		-24.32	-50.62	75042
Tema	GH		5.67	-0.02	155782
Tema New Town	GH		5.65	0.03	95837
Temara	MA		33.93	-6.91	342345
Temecula	US	California	33.49	-117.15	110003
Temerluh	MY		3.45	102.42	59916
Temirtau	KZ		50.05	72.95	170600
Temixco	MX		18.85	-99.23	97788
Tempe	US	Arizona	33.41	-111.91	175826
Tempe Junction	US	Arizona	33.41	-111.94	158368
Tempelhof	DE		52.47	13.40	61769
Temple	US	Texas	31.10	-97.34	72277
Temple City	US	California	34.11	-118.06	36365
Temple Terrace	US	Florida	28.04	-82.39	25731
Templeogue	IE		53.30	-6.31	18076
Templestowe	AU		-37.75	145.15	16966
Templeton-Est	CA		45.49	-75.59	20000
Temuco	CL		-38.74	-72.60	238129
Tendō	JP		38.35	140.37	65393
Tengréla	CI		10.48	-6.41	52271
Tengyue	CN		24.99	98.51	127133
Teni	IN		10.01	77.48	1034724
Tenkodogo	BF		11.78	-0.37	61936
Tennala	IN		10.99	75.94	56546
Tenri	JP		34.58	135.83	71052
Teoloyucan	MX		19.74	-99.18	51255
Tepatitlán de Morelos	MX		20.82	-102.76	91959
Tepeji del Río de Ocampo	MX		19.90	-99.34	80612
Tepexpan	MX		19.61	-98.94	102667
Tepic	MX		21.51	-104.89	332863
Teplice	CZ		50.64	13.82	50912
Teramo	IT		42.66	13.70	54338
Terbanggi Besar	ID		-4.88	105.22	52566
Teresina	BR		-5.09	-42.80	871126
Teresópolis	BR		-22.42	-42.98	176692
Ternate	ID		0.79	127.38	210836
Terni	IT		42.56	12.64	111189
Ternopil	UA		49.55	25.59	225238
Terrace	CA		54.52	-128.60	19443
Terrace Heights	US	New York	40.72	-73.77	15421
Terrassa	ES		41.57	2.02	218535
Terre Haute	US	Indiana	39.47	-87.41	60825
Terrebonne	CA		45.70	-73.65	111575
Terrell	US	Texas	32.74	-96.28	16981
Terrytown	US	Louisiana	29.91	-90.03	23319
Teshi Old Town	GH		5.58	-0.11	144013
Tessaoua	NE		13.76	7.99	58750
Tete	MZ		-16.16	33.59	357000
Tetovo	MK		42.01	20.97	63176
Tetuán de las Victorias	ES		40.46	-3.70	155000
Tewkesbury	GB		51.99	-2.16	20360
Tewksbury	US	Massachusetts	42.61	-71.23	29326
Texarkana	US	Texas	33.43	-94.05	37280
Texarkana	US	Arkansas	33.44	-94.04	30353
Texas City	US	Texas	29.38	-94.90	47618
Texcoco de Mora	MX		19.51	-98.88	105165
Teziutlan	MX		19.82	-97.36	103583
Tezpur	IN		26.63	92.80	75540
Teófilo Otoni	BR		-17.86	-41.51	101170
Tha Maka	TH		13.90	99.77	52907
Tha Raeng	TH		13.87	100.65	97658
Thaba Nchu	ZA		-29.21	26.84	72721
Thakhèk	LA		17.41	104.83	90800
Thamesmead	GB		51.50	0.12	31824
Thanbyuzayat	MM		15.97	97.73	57208
Thanh Hóa	VN		19.80	105.77	850000
Thanh Khê	VN		16.07	108.19	201240
Thanh Liệt	VN		20.97	105.82	76238
Thanh Xuân	VN		20.99	105.80	293292
Thanhlyin	MM		16.78	96.25	78667
Thanjavur	IN		10.79	79.14	291067
Thanlyin	MM		16.77	96.25	69448
Tharyarwady	MM		17.65	95.79	54386
Thatcham	GB		51.40	-1.26	25464
Thaton	MM		16.92	97.37	123727
Thawi Watthana	TH		13.78	100.38	76351
Thayetmyo	MM		19.32	95.18	98185
The Acreage	US	Florida	26.79	-80.27	38704
The Beaches	CA		43.67	-79.30	21567
The Bronx	US	New York	40.85	-73.87	1385108
The Colony	US	Texas	33.09	-96.89	41779
The Crossings	US	Florida	25.67	-80.40	22758
The Dalles	US	Oregon	45.59	-121.18	15340
The Gap	AU		-27.44	152.94	16371
The Hague	NL		52.08	4.30	474292
The Hammocks	US	Florida	25.67	-80.44	51003
The Trails of Frisco	US	Texas	33.16	-96.87	51059
The Valley	AI		18.22	-63.06	2035
The Villages	US	Florida	28.93	-81.96	51442
The Woodlands	US	Texas	30.16	-95.49	93847
Thembisa	ZA		-26.00	28.23	511655
Thenali	IN		16.24	80.64	164937
Thenkasi	IN		8.96	77.32	70545
Thessaloníki	GR		40.64	22.93	317778
Thetford	GB		52.42	0.75	24833
Thetford-Mines	CA		46.09	-71.31	25704
Thika	KE		-1.03	37.07	251407
Thimphu	BT		27.47	89.64	98676
Thiruvananthapuram	IN		8.49	76.95	788271
Thiruvarur	IN		10.77	79.64	58777
Thiès	SN		14.79	-16.93	317763
Thiès Nones	SN		14.78	-16.97	252320
Thodupuzha	IN		9.89	76.72	52045
Thohoyandou	ZA		-22.95	30.48	107144
Thomastown	AU		-37.68	145.02	20234
Thomasville	US	North Carolina	35.88	-80.08	27061
Thomasville	US	Georgia	30.84	-83.98	18742
Thomazeau	HT		18.65	-72.09	52017
Thon Buri	TH		13.72	100.49	119708
Thongwa	MM		16.76	96.52	52496
Thoothukudi	IN		8.77	78.13	410760
Thornaby-on-Tees	GB		54.53	-1.30	22356
Thornbury	AU		-37.76	145.01	19005
Thorncliffe Park	CA		43.71	-79.35	21108
Thorne	GB		53.61	-0.96	17295
Thornlie	AU		-32.06	115.95	23665
Thornton	US	Colorado	39.87	-104.97	133451
Thornton-Cleveleys	GB		53.87	-3.02	31157
Thorold	CA		43.12	-79.20	18801
Thousand Oaks	US	California	34.17	-118.84	129339
Three Lakes	US	Florida	25.64	-80.40	15047
Thrissur	IN		10.52	76.22	315957
Throgs Neck	US	New York	40.82	-73.82	33683
Thul	PK		28.24	68.78	88554
Thunder Bay	CA		48.38	-89.25	108843
Thung Khru	TH		13.63	100.51	116473
Thuqbah	SA		26.26	50.20	248888
Thuận An	VN		10.92	106.71	588616
Thuận Thanh	VN		21.05	106.08	199577
Thành Phố Bà Rịa	VN		10.50	107.17	235192
Thành phố Sông Công	VN		21.48	105.84	128357
Thành Phố Uông Bí	VN		21.03	106.77	63829
Thái Bình	VN		20.45	106.34	53071
Thái Hòa	VN		18.92	104.97	66127
Thái Nguyên	VN		21.59	105.85	420000
Thākurgaon	BD		26.03	88.47	71096
Thāne	IN		19.20	72.96	1841488
Thānesar	IN		29.97	76.83	155152
Thượng Cát	VN		21.09	105.73	87406
Thị Trấn Mạo Khê	VN		21.06	106.59	72012
Thị Trấn Phước Bửu	VN		10.53	107.40	51895
Thị Trấn Thuận Châu	VN		21.44	103.69	153000
Thị Trấn Đông Triều	VN		21.08	106.51	248896
Thị Trấn Đại Từ	VN		21.63	105.64	179192
Thốt Nốt	VN		10.27	105.53	158225
Thới Lai	VN		10.07	105.56	109684
Thủ Dầu Một	VN		10.98	106.65	373105
Thủ Đức	VN		10.85	106.77	524670
Tianchang	CN		38.00	114.02	61292
Tianfu	CN		37.26	122.05	115370
Tianguá	BR		-3.73	-40.99	81506
Tianjin	CN		39.14	117.18	11090314
Tianliu	CN		37.00	118.78	67165
Tianpeng	CN		30.99	103.94	60797
Tianshui	CN		34.58	105.74	1212791
Tianzhuang	CN		36.80	119.74	64957
Tiaret	DZ		35.37	1.32	178915
Tiefu	CN		34.53	118.03	87689
Tieli	CN		46.98	128.05	107621
Tieling	CN		42.29	123.84	333907
Tiffin	US	Ohio	41.11	-83.18	17687
Tiflet	MA		33.89	-6.31	94684
Tifton	US	Georgia	31.45	-83.51	16725
Tigard	US	Oregon	45.43	-122.77	51253
Tigwav	HT		18.43	-72.87	117504
Tijuana	MX		32.50	-117.00	1922523
Tijucas	BR		-27.24	-48.63	51592
Tikhoretsk	RU		45.85	40.12	64387
Tikhvin	RU		59.64	33.53	62075
Tiko	CM		4.08	9.36	94836
Tilburg	NL		51.56	5.09	221947
Tilhar	IN		27.96	79.74	57043
Tillmans Corner	US	Alabama	30.59	-88.17	17398
Tillsonburg	CA		42.86	-80.73	18615
Timaru	NZ		-44.40	171.25	29300
Timashyovsk	RU		45.62	38.95	53940
Timbuktu	ML		16.77	-3.01	84208
Times Square	US	New York	40.76	-73.99	17749
Timika	ID		-4.61	136.68	142909
Timişoara	RO		45.75	21.23	250849
Timmins	CA		48.47	-81.33	41788
Timon	BR		-5.09	-42.84	174465
Timóteo	BR		-19.58	-42.65	81579
Tin Shui Wai	HK		22.46	114.00	286232
Tinaquillo	VE		9.92	-68.30	115937
Tindivanam	IN		12.23	79.66	72796
Tingo María	PE		-9.30	-76.00	53177
Tinley Park	US	Illinois	41.57	-87.78	57143
Tinongan	PH		10.21	123.04	62146
Tinsukia	IN		27.49	95.36	116322
Tinton Falls	US	New Jersey	40.30	-74.10	17772
Tipitapa	NI		12.20	-86.10	50000
Tipton	GB		52.53	-2.07	47000
Tiptūr	IN		13.26	76.48	60957
Tiquipaya	BO		-17.34	-66.22	62675
Tirana	AL		41.33	19.82	418495
Tiraspol	MD		46.84	29.63	157000
Tirhanimîne	MA		35.24	-3.95	55827
Tirmiz	UZ		37.22	67.28	182800
Tiruchengode	IN		11.38	77.89	95335
Tiruchirappalli	IN		10.82	78.70	1022518
Tirumangalam	IN		9.82	77.98	51194
Tirunelveli	IN		8.73	77.68	1435844
Tirupati	IN		13.64	79.42	295323
Tirupattur	IN		12.49	78.57	64125
Tirupparangunram	IN		9.88	78.07	50004
Tiruppur	IN		11.12	77.35	963173
Tirur	IN		10.91	75.92	56058
Tiruttangal	IN		9.48	77.83	55362
Tiruvalla	IN		9.38	76.57	57223
Tiruvallur	IN		13.14	79.91	56074
Tiruvannamalai	IN		12.23	79.07	145278
Tiruvottiyūr	IN		13.16	80.30	249446
Tirūrangādi	IN		11.04	75.92	56632
Tissemsilt	DZ		35.61	1.81	66084
Titirangi	NZ		-36.94	174.66	15490
Titiwangsa	MY		3.18	101.70	122096
Titusville	US	Florida	28.61	-80.81	45393
Titāgarh	IN		22.74	88.37	127751
Tiu Keng Leng	HK		22.30	114.25	51751
Tivaouane	SN		14.95	-16.82	102658
Tiverton	GB		50.90	-3.49	22291
Tizi Ouzou	DZ		36.71	4.05	104312
Tiznit	MA		29.70	-9.73	81569
Tiébo	SN		14.63	-16.23	100289
Tlalnepantla	MX		19.54	-99.20	653410
Tlalpan	MX		19.30	-99.16	574577
Tlaquepaque	MX		20.64	-103.29	650123
Tlaxcala	MX		19.32	-98.24	84670
Tlemcen	DZ		34.88	-1.31	173531
Tlokweng	BW		-24.67	25.97	55508
Tláhuac	MX		19.29	-99.01	305076
Toa Payoh New Town	SG		1.34	103.85	120650
Toamasina	MG		-18.15	49.40	345107
Toba Tek Singh	PK		30.97	72.48	123102
Tobias Barreto	BR		-11.18	-38.00	50905
Tobolsk	RU		58.20	68.25	113800
Tobruk	LY		32.09	23.95	141499
Tochigi	JP		36.38	139.73	159056
Tocoa	HN		15.68	-86.00	111972
Tocumen	PA		9.09	-79.38	50844
Tohāna	IN		29.71	75.90	63871
Tokat	TR		40.31	36.55	129702
Toki	JP		35.35	137.18	58567
Tokmok	KG		42.84	75.30	71443
Tokoname	JP		34.88	136.85	58710
Tokorozawa	JP		35.80	139.47	344194
Tokoza	ZA		-26.36	28.13	106000
Tokushima	JP		34.07	134.57	267345
Tokuyama	JP		34.05	131.82	101133
Tokyo	JP		35.69	139.69	9733276
Toledo	US	Ohio	41.66	-83.56	265638
Toledo	PH		10.38	123.64	206692
Toledo	BR		-24.71	-53.74	119313
Toledo	ES		39.86	-4.02	86526
Tolga	DZ		34.72	5.38	50575
Toli-Toli	ID		1.04	120.82	242783
Toliara	MG		-23.35	43.67	178725
Toluca	MX		19.29	-99.65	489333
Tolyatti	RU		53.53	49.35	702879
Tomakomai	JP		42.64	141.60	174806
Tomaszów Mazowiecki	PL		51.53	20.01	67197
Tome	JP		38.71	141.16	77897
Tomigusuku	JP		26.19	127.68	64612
Tomiya	JP		38.39	140.89	52433
Toms River	US	New Jersey	39.95	-74.20	88791
Tomsk	RU		56.50	84.98	574002
Tomé	CL		-36.62	-72.96	53219
Tomé-Açu	BR		-2.42	-48.15	67585
Tonalá	MX		20.62	-103.24	408759
Tonbridge	GB		51.20	0.27	36115
Tondabayashichō	JP		34.50	135.60	132873
Tongaat	ZA		-29.57	31.12	64829
Tongchuan	CN		34.90	108.95	417740
Tongchuan	CN		31.09	105.09	58346
Tongchuanshi	CN		35.07	109.08	223603
Tonghua	CN		41.72	125.93	510000
Tongliao	CN		43.61	122.27	261110
Tongling	CN		30.95	117.78	402062
Tongren	CN		35.51	102.02	103700
Tongren	CN		27.72	109.19	90593
Tongshan	CN		34.18	117.16	329661
Tongyeong	KR		34.85	128.43	70641
Tongzhou	CN		39.90	116.66	163326
Tonk	IN		26.17	75.79	165294
Tonypandy	GB		51.62	-3.46	62545
Tooele	US	Utah	40.53	-112.30	33157
Tooting	GB		51.43	-0.16	16239
Toowoomba	AU		-27.56	151.95	142163
Topeka	US	Kansas	39.05	-95.68	125963
Topi	PK		34.07	72.62	74867
Torbalı	TR		38.18	27.34	50303
Torbat-e Jām	IR		35.24	60.62	58928
Torbat-e Ḩeydarīyeh	IR		35.27	59.22	125633
Tordher	PK		33.99	72.29	150000
Toride	JP		35.90	140.08	104524
Toronto	CA		43.71	-79.40	2794356
Torquay	GB		50.46	-3.53	65388
Torquay	AU		-38.33	144.33	18534
Torrance	US	California	33.84	-118.34	143592
Torre del Greco	IT		40.79	14.37	85332
Torrejón de Ardoz	ES		40.46	-3.47	118162
Torrelavega	ES		43.35	-4.05	55297
Torremolinos	ES		36.62	-4.50	65448
Torrent	ES		39.44	-0.47	78543
Torrevieja	ES		37.98	-0.68	82599
Torreón	MX		25.54	-103.42	735340
Torrington	US	Connecticut	41.80	-73.12	34906
Toruń	PL		53.01	18.60	196935
Toshima	JP		35.76	139.74	301599
Tosu	JP		33.37	130.52	74196
Totonicapán	GT		14.91	-91.36	103952
Tottenham	GB		51.60	-0.07	130000
Tottenham Hale	GB		51.59	-0.06	15064
Totteridge	GB		51.63	-0.20	15159
Totton	GB		50.92	-1.49	34169
Tottori-shi	JP		35.50	134.23	188465
Touba	SN		14.86	-15.88	1120824
Toufen	TW		24.69	120.91	106310
Touggourt	DZ		33.11	6.07	143270
Toulon	FR		43.12	5.93	168701
Toulouse	FR		43.60	1.44	511684
Toumodi	CI		6.56	-5.02	55986
Tourcoing	FR		50.72	3.16	99160
Tournai	BE		50.61	3.39	69554
Tours	FR		47.39	0.70	141621
Towada	JP		40.62	141.21	60697
Town 'n' Country	US	Florida	28.01	-82.58	78442
Townline	CA		49.06	-122.36	21095
Townsville	AU		-19.27	146.81	201313
Towson	US	Maryland	39.40	-76.60	55197
Toyama	JP		36.70	137.22	415844
Toyoake	JP		35.04	137.00	69295
Toyohashi	JP		34.77	137.38	377453
Toyokawa	JP		34.82	137.40	184661
Toyonaka	JP		34.78	135.47	401558
Toyooka	JP		35.54	134.82	78348
Toyota	JP		35.08	137.15	426162
Trabzon	TR		41.01	39.73	244083
Tracy	US	California	37.74	-121.43	87075
Trairi	BR		-3.28	-39.27	58415
Tralee	IE		52.27	-9.70	26079
Tramandaí	BR		-29.98	-50.13	54387
Trang	TH		7.56	99.61	66713
Trani	IT		41.28	16.41	53981
Trapani	IT		38.02	12.54	67531
Traralgon	AU		-38.20	146.54	26907
Traverse City	US	Michigan	44.76	-85.62	15218
Trelew	AR		-43.25	-65.31	97915
Tremembé	BR		-22.96	-45.55	51173
Tremont	US	New York	40.85	-73.91	22870
Trento	IT		46.07	11.12	120709
Trenton	US	New Jersey	40.22	-74.74	89620
Trenton	US	Michigan	42.14	-83.18	18380
Trenčín	SK		48.89	18.04	58278
Treptow	DE		52.49	13.44	50000
Tres Arroyos	AR		-38.38	-60.28	52199
Treviso	IT		45.67	12.24	85760
Tri-Cities	US	Washington	46.25	-119.20	244036
Trichardt	ZA		-26.49	29.23	52776
Trier	DE		49.76	6.64	100129
Trieste	IT		45.65	13.78	204338
Trincomalee	LK		8.58	81.23	108420
Trindade	BR		-16.65	-49.49	142431
Trinidad	BO		-14.83	-64.90	84259
Trinidad	CU		21.80	-79.98	60206
Trinity-Bellwoods	CA		43.65	-79.41	16556
Tripoli	LY		32.89	13.19	1302947
Tripoli	LB		34.43	35.84	229398
Tripunittura	IN		9.94	76.33	69390
Triyuga	NP		26.79	86.70	71405
Trnava	SK		48.38	17.59	62806
Trois-Rivières	CA		46.35	-72.55	144472
Troisdorf	DE		50.81	7.15	74749
Troitsk	RU		54.09	61.57	82338
Trondheim	NO		63.43	10.40	216518
Troparëvo	RU		55.66	37.48	118000
Trotwood	US	Ohio	39.80	-84.31	24096
Troutdale	US	Oregon	45.54	-122.39	16631
Trowbridge	GB		51.32	-2.21	40952
Troy	US	Michigan	42.61	-83.15	83280
Troy	US	New York	42.73	-73.69	49906
Troy	US	Ohio	40.04	-84.20	25659
Troy	US	Alabama	31.81	-85.97	18853
Troyes	FR		48.30	4.09	60785
Truckee	US	California	39.33	-120.18	16299
Truganina	AU		-37.82	144.75	36305
Trujillo	PE		-8.12	-79.03	1067700
Trujillo	VE		9.37	-70.44	71362
Trujillo Alto	PR		18.35	-66.01	75243
Trumbull	US	Connecticut	41.24	-73.20	36018
Truro	GB		50.27	-5.05	23041
Trussville	US	Alabama	33.62	-86.61	21023
Trà Vinh	VN		9.95	106.34	160310
Três Corações	BR		-21.70	-45.25	75485
Três Lagoas	BR		-20.79	-51.70	78712
Três Pontas	BR		-21.37	-45.51	55255
Três Rios	BR		-22.12	-43.21	82300
Tríkala	GR		39.55	21.77	61653
Trảng Bom	VN		10.95	107.01	57560
Trảng Bàng	VN		11.03	106.36	161831
Trần Văn Thời	VN		9.08	104.98	55897
Tsaritsyno	RU		55.63	37.65	123000
Tsawwassen	CA		49.02	-123.08	21588
Tsentralno-Miskyi	UA		48.30	38.03	118283
Tsentralno-Miskyi	UA		48.06	37.97	94417
Tsentralnyi	UA		47.10	37.55	179582
Tseung Kwan O	HK		22.33	114.25	412900
Tshela	CD		-5.00	12.95	64210
Tshikapa	CD		-6.42	20.80	634529
Tshilenge	CD		-10.97	22.90	116073
Tsing Yi Town	HK		22.35	114.10	182100
Tsu	JP		34.73	136.52	274537
Tsubame	JP		37.66	138.93	77382
Tsuchiura	JP		36.09	140.21	144399
Tsuen Wan	HK		22.37	114.11	318916
Tsukuba	JP		36.08	140.12	241656
Tsuruga	JP		35.65	136.06	68482
Tsurugashima	JP		35.96	139.40	70117
Tsuruoka	JP		38.72	139.82	125389
Tsurusaki	JP		33.25	131.69	76968
Tsushima	JP		35.17	136.72	67658
Tsuyama	JP		35.05	134.00	102294
Tsévié	TG		6.43	1.21	55775
Tual	ID		-5.63	132.75	90470
Tualatin	US	Oregon	45.38	-122.76	27154
Tuanbao	CN		30.34	109.13	59580
Tuapse	RU		44.10	39.08	64234
Tuban	ID		-6.90	112.06	76242
Tubarão	BR		-28.47	-49.01	110088
Tubod	PH		8.06	123.79	50395
Tuckahoe	US	Virginia	37.59	-77.56	44990
Tucker	US	Georgia	33.85	-84.22	27581
Tucson	US	Arizona	32.22	-110.93	542629
Tucupita	VE		9.06	-62.05	99778
Tucuruvi	BR		-23.48	-46.61	99559
Tucuruí	BR		-3.77	-49.68	91306
Tuen Mun	HK		22.39	113.97	507900
Tuggeranong	AU		-35.42	149.07	89461
Tuguegarao	PH		17.62	121.72	167297
Tujunga	US	California	34.25	-118.29	26527
Tukuyu	TZ		-9.25	33.65	50000
Tukwila	US	Washington	47.47	-122.26	20018
Tula	RU		54.20	37.62	482873
Tulancingo	MX		20.08	-98.36	102406
Tulangan Utara	ID		-7.47	112.65	63889
Tulare	US	California	36.21	-119.35	62315
Tulcea	RO		45.18	28.81	65624
Tulcán	EC		0.81	-77.72	86498
Tullahoma	US	Tennessee	35.36	-86.21	19128
Tullamore	IE		53.27	-7.49	15598
Tulsa	US	Oklahoma	36.15	-95.99	413066
Tultepec	MX		19.68	-99.13	65338
Tulun	RU		54.57	100.58	51330
Tulungagung	ID		-8.07	111.90	65262
Tuluá	CO		4.08	-76.20	221684
Tumaco	CO		1.79	-78.79	86713
Tumbes	PE		-3.56	-80.44	96946
Tumen	CN		42.97	129.84	78719
Tumkūr	IN		13.34	77.10	307359
Tumwater	US	Washington	47.01	-122.91	19190
Tumxuk	CN		39.87	79.06	135727
Tunasan	PH		14.38	121.05	61374
Tunduma	TZ		-9.30	32.77	219309
Tung Chung	HK		22.29	113.94	114100
Tungi	BD		23.89	90.40	337579
Tungipara	BD		22.90	89.90	114482
Tuni	IN		17.36	82.55	53425
Tunis	TN		36.82	10.17	693210
Tunja	CO		5.54	-73.36	172548
Tupelo	US	Mississippi	34.26	-88.70	35680
Tupi	PH		6.33	124.95	78599
Tupã	BR		-21.93	-50.51	63928
Tura	IN		25.51	90.20	74858
Turbaco	CO		10.33	-75.41	56171
Turbat	PK		26.00	63.05	75694
Turbo	CO		8.09	-76.73	50508
Turgutlu	TR		38.50	27.70	103292
Turhal	TR		40.39	36.08	110884
Turin	IT		45.07	7.69	847287
Turkistan	KZ		43.29	68.26	227098
Turku	FI		60.45	22.27	206655
Turlock	US	California	37.49	-120.85	72292
Turmero	VE		10.23	-67.47	344700
Turpan	CN		42.95	89.18	273385
Tuscaloosa	US	Alabama	33.21	-87.57	111338
Tuscany	CA		51.12	-114.24	19700
Tustin	US	California	33.75	-117.83	80583
Tustin Legacy	US	California	33.70	-117.83	21428
Tutóia	BR		-2.76	-42.27	53356
Tuxtepec	MX		18.09	-96.13	159452
Tuxtla	MX		16.75	-93.12	604147
Tuy Hòa	VN		13.10	109.32	155921
Tuymazy	RU		54.61	53.71	68829
Tuyên Quang	VN		21.82	105.21	104645
Tuzla	BA		44.54	18.67	142486
Tver	RU		56.86	35.90	420065
Twentynine Palms	US	California	34.14	-116.05	26025
Twifu Praso	GH		5.61	-1.55	100851
Twin Falls	US	Idaho	42.56	-114.46	47468
Twinsburg	US	Ohio	41.31	-81.44	18872
Tychy	PL		50.14	18.97	130000
Tyldesley	GB		53.51	-2.47	35932
Tyler	US	Texas	32.35	-95.30	103700
Tynemouth	GB		55.02	-1.43	60605
Tyoply Stan	RU		55.62	37.49	125000
Tyre	LB		33.27	35.19	135204
Tysons	US	Virginia	38.92	-77.23	19627
Tyumen	RU		57.15	65.53	768358
Táriba	VE		7.82	-72.22	138402
Tân An	VN		10.54	106.41	215250
Tân Bình	VN		10.80	106.66	89373
Tân Châu	VN		10.80	105.24	175211
Tân Uyên	VN		11.08	106.79	52873
Târgovişte	RO		44.93	25.46	66965
Târgu Jiu	RO		45.05	23.28	73545
Târgu Mureş	RO		46.54	24.56	212752
Tây Hồ	VN		21.07	105.81	168300
Tây Ninh	VN		11.31	106.10	135254
Täby	SE		59.44	18.07	58123
Tébessa	DZ		35.40	8.12	194461
Tétouan	MA		35.58	-5.37	415810
Tôlanaro	MG		-25.03	46.98	71258
Tønsberg	NO		59.27	10.41	55387
Túxpam de Rodríguez Cano	MX		20.96	-97.41	84750
Tübingen	DE		48.52	9.05	92322
Türkmenabat	TM		39.07	63.58	230861
Türkmenbaşy	TM		40.02	52.96	91745
Tādepalle	IN		16.48	80.60	64149
Tājūrā’	LY		32.88	13.35	100000
Tākestān	IR		36.07	49.70	71499
Tāndoni	IN		10.93	78.09	53854
Tāndā	IN		26.55	82.66	88073
Tārūt	SA		26.57	50.04	85371
Tēpī	ET		7.20	35.45	66700
Tīkamgarh	IN		24.74	78.83	79106
Tōgane	JP		35.55	140.37	66332
Tōkai	JP		35.02	136.91	113787
Tōkamachi	JP		37.13	138.77	53333
Tŏkch’ŏn	KP		39.75	126.26	237133
Tūndla	IN		27.21	78.24	50939
Tūyserkān	IR		34.55	48.44	50455
Tŭytepa	UZ		41.03	69.36	51400
Tịnh Biên	VN		10.60	104.94	143098
Từ Sơn	VN		21.10	105.97	65697
T’aet’an-ŭp	KP		38.09	125.30	64258
Ualog	PH		10.57	123.39	60548
Ubatuba	BR		-23.43	-45.07	91824
Ubauro	PK		28.16	69.73	50981
Ube	JP		33.94	131.25	173733
Uberaba	BR		-19.75	-47.93	337836
Uberlândia	BR		-18.92	-48.28	563536
Ubon Ratchathani	TH		15.24	104.85	122533
Ubud	ID		-8.51	115.27	74800
Ubá	BR		-21.12	-42.94	103365
UC Irvine	US	California	33.64	-117.84	15807
Uccle	BE		50.80	4.34	82929
Uckfield	GB		50.97	0.10	18452
Udaipur	IN		24.59	73.71	451100
Udgīr	IN		18.39	77.12	103550
Udhampur	IN		32.92	75.14	84015
Udine	IT		46.07	13.24	100170
Udon Thani	TH		17.42	102.79	130531
Udumalaippettai	IN		10.59	77.25	61133
Udupi	IN		13.33	74.75	165000
Ueda	JP		36.40	138.28	157480
Ueno-ebisumachi	JP		34.76	136.13	61598
Ufa	RU		54.74	55.97	1120547
Uga	NG		5.94	7.08	64179
Ugep	NG		5.81	8.08	200276
Ughelli	NG		5.49	6.00	79986
Uijeongbu-si	KR		37.74	127.05	479141
Uiju	KP		40.20	124.53	50081
Uiwang	KR		37.37	126.95	63040
Ujhāni	IN		28.00	79.01	56309
Uji	JP		34.89	135.80	192925
Ujjain	IN		23.18	75.78	515215
Ukhta	RU		63.57	53.69	102187
Uki	JP		32.62	130.66	59928
Ukiah	US	California	39.15	-123.21	15917
Ukunda	KE		-4.29	39.56	77686
Ulan Bator	MN		47.91	106.88	844818
Ulan-Ude	RU		51.83	107.60	360278
Ulanhot	CN		46.08	122.08	165846
Ulanqab	CN		40.99	113.13	550231
Ulhasnagar	IN		19.22	73.15	516584
Ullagaram	IN		12.98	80.20	53322
Ullal	IN		12.81	74.86	59116
Ulm	DE		48.40	9.99	120451
Ulsan	KR		35.54	129.32	1098421
Ulu Bedok	SG		1.33	103.93	276990
Ulu Tiram	MY		1.60	103.82	75350
Uluberiya	IN		22.48	88.10	235345
Ulyanovsk	RU		54.33	48.39	626540
Uman	UA		48.75	30.22	81525
Umarkot	PK		25.36	69.74	144558
Umeå	SE		63.83	20.26	130224
Umina Beach	AU		-33.52	151.31	16413
Umm Al Quwain City	AE		25.56	55.56	59098
Umm el Faḥm	IL		32.52	35.15	56109
Umm Qaşr	IQ		30.04	47.92	107620
Umm Ruwaba	SD		12.91	31.22	56833
Umraniye	TR		41.02	29.12	573265
Umred	IN		20.85	79.32	53971
Umuahia	NG		5.52	7.49	370000
Umuarama	BR		-23.77	-53.33	117095
Una	IN		20.82	71.04	58528
Unaizah	SA		26.10	44.00	183319
Unaí	BR		-16.36	-46.91	86619
Ungaran	ID		-7.14	110.41	171378
Ungsang	KR		35.41	129.17	83360
Union	US	New Jersey	40.70	-74.26	56771
Union City	US	California	37.60	-122.02	74494
Union City	US	New Jersey	40.78	-74.02	69156
Union City	US	Georgia	33.59	-84.54	20805
Union Hill-Novelty Hill	US	Washington	47.68	-122.03	18805
Uniondale	US	New York	40.70	-73.59	24759
Unionport	US	New York	40.83	-73.85	23895
Universal City	US	California	34.14	-118.35	105000
Universal City	US	Texas	29.55	-98.29	19986
University	US	Florida	28.07	-82.44	41163
University City	US	Missouri	38.66	-90.31	35058
University City	US	Pennsylvania	39.95	-75.19	17578
University Endowment Lands	CA		49.26	-123.24	16920
University Heights	CA		52.14	-106.58	51957
University Heights	US	New York	40.86	-73.91	27935
University of Texas	US	Texas	30.29	-97.74	53082
University Park	US	Florida	25.75	-80.37	26995
University Park	US	Texas	32.85	-96.80	24759
University Place	US	Washington	47.24	-122.55	32842
Universitäts- und Hansestadt Greifswald	DE		54.09	13.40	52731
União da Vitória	BR		-26.23	-51.09	55033
União dos Palmares	BR		-9.16	-36.03	60874
Unjha	IN		23.80	72.39	57108
Unna	DE		51.54	7.69	66734
Unnāo	IN		26.55	80.49	161671
Untolovo	RU		60.01	30.21	50000
Upata	VE		8.02	-62.41	112617
Upington	ZA		-28.45	21.26	71373
Upland	US	California	34.10	-117.65	76443
Upleta	IN		21.74	70.28	58775
Uppal Kalan	IN		17.41	78.56	118259
Upper Alton	US	Illinois	38.91	-90.15	29251
Upper Arlington	US	Ohio	39.99	-83.06	34907
Upper Coomera	AU		-27.88	153.29	24956
Upper Gilgil	KE		-0.21	36.27	60711
Upper Hutt	NZ		-41.14	175.05	47400
Upper Norwood	GB		51.42	-0.09	16082
Upper Saint Clair	US	Pennsylvania	40.34	-80.08	19229
Upper West Side	US	New York	40.79	-73.98	226989
Uppsala	SE		59.86	17.64	177074
Uptown	US	Illinois	41.97	-87.65	55137
Urasoe	JP		26.26	127.73	115690
Urayasu	JP		35.66	139.90	171362
Urbana	US	Illinois	40.11	-88.21	42311
Urbandale	US	Iowa	41.63	-93.71	44062
Urdaneta	PH		15.98	120.57	145935
Ureña	VE		7.92	-72.44	56509
Urganch	UZ		41.55	60.63	145000
Urgut Shahri	UZ		39.42	67.26	65300
Uriangato	MX		20.14	-101.18	51382
Uritsk	RU		59.84	30.18	55037
Urla	TR		38.32	26.76	62989
Urmston	GB		53.45	-2.35	41731
Uromi	NG		6.70	6.33	108608
Ursynów	PL		52.15	21.05	149775
Uruapan	MX		19.42	-102.06	299523
Uruguaiana	BR		-29.75	-57.09	123480
Uruma	JP		26.38	127.86	125303
Urun-Islāmpur	IN		17.05	74.27	67391
Usera	ES		40.39	-3.70	141189
Ushiku	JP		35.97	140.13	84651
Ushirombo	TZ		-3.49	31.96	95052
Ushuaia	AR		-54.81	-68.32	56825
Usol’ye-Sibirskoye	RU		52.75	103.65	85900
Ussuriysk	RU		43.80	131.96	157068
Ust-Kamenogorsk	KZ		49.97	82.61	319067
Usta Muhammad	PK		28.18	68.04	64632
Ust’-Ilimsk	RU		58.00	102.66	100271
Usulután	SV		13.34	-88.44	51910
Utengule	TZ		-8.90	33.33	50000
Utica	US	New York	43.10	-75.23	61100
Utrecht	NL		52.09	5.12	376435
Utrera	ES		37.19	-5.78	52617
Utsunomiya	JP		36.57	139.88	518757
Uttaradit	TH		17.63	100.09	58313
Uvalde	US	Texas	29.21	-99.79	16476
Uvira	CD		-3.40	29.14	407092
Uwajima	JP		33.22	132.56	70809
Uxbridge	GB		51.55	-0.48	70000
Uxbridge	CA		44.10	-79.12	21176
Uyo	NG		5.05	7.93	436606
Uyovu	TZ		-3.28	31.53	60849
Uzhhorod	UA		48.62	22.29	115449
Uzlovaya	RU		53.98	38.16	58458
Uíge	AO		-7.61	15.06	322531
Uşak	TR		38.67	29.41	369433
Užice	RS		43.86	19.85	63577
Vaasa	FI		63.10	21.62	69819
Vacaria	BR		-28.51	-50.93	64197
Vacaville	US	California	38.36	-121.99	96803
Vacoas	MU		-20.30	57.48	115289
Vadodara	IN		22.30	73.21	1822221
Vaduz	LI		47.14	9.52	5197
Vagonoremont	RU		55.90	37.55	50000
Val Dor	MY		5.25	100.49	88600
Val-d'Or	CA		48.10	-77.80	25541
Val-des-Arbres	CA		45.60	-73.68	40974
Valdefuentes	ES		40.49	-3.64	69176
Valdemoro	ES		40.19	-3.68	74745
Valdivia	CL		-39.81	-73.25	133419
Valdosta	US	Georgia	30.83	-83.28	55724
Vale of Leven	GB		55.97	-4.58	24640
Valence	FR		44.93	4.91	63864
Valencia	VE		10.16	-68.00	1619470
Valencia	ES		39.47	-0.38	824340
Valencia	US	California	34.44	-118.61	148456
Valenzuela	PH		14.70	120.97	725173
Valença	BR		-13.37	-39.07	85655
Valença	BR		-22.25	-43.70	71462
Valera	VE		9.32	-70.60	244708
Valinda	US	California	34.05	-117.94	22822
Valinhos	BR		-22.97	-47.00	126373
Valjevo	RS		44.28	19.90	61035
Valladolid	ES		41.66	-4.72	300618
Valle de La Pascua	VE		9.22	-66.01	153136
Valle de Santiago	MX		20.39	-101.19	68058
Vallecas	ES		40.38	-3.62	53208
Valledupar	CO		10.47	-73.25	490075
Vallejo	US	California	38.10	-122.26	121692
Valletta	MT		35.90	14.51	6794
Valley East	CA		46.64	-81.00	17451
Valley Glen	US	California	34.19	-118.42	60000
Valley Station	US	Kentucky	38.11	-85.87	22756
Valley Stream	US	New York	40.66	-73.71	37962
Valparai	IN		10.33	76.95	90353
Valparaiso	US	Indiana	41.47	-87.06	32626
Valparaíso	CL		-33.04	-71.63	282448
Valparaíso de Goiás	BR		-16.07	-47.98	198861
Valrico	US	Florida	27.94	-82.24	35545
Valsād	IN		20.61	72.93	139764
Valvedditturai	LK		9.82	80.17	78205
Valverde	ES		40.50	-3.68	64757
Van	TR		38.49	43.38	525016
Van Buren	US	Arkansas	35.44	-94.35	23081
Van Nest	US	New York	40.85	-73.86	23700
Van Nuys	US	California	34.19	-118.45	136443
Vanadzor	AM		40.81	44.50	78100
Vancouver	CA		49.25	-123.12	662248
Vancouver	US	Washington	45.64	-122.66	196442
Vandalia	US	Ohio	39.89	-84.20	15106
Vanderbijlpark	ZA		-26.71	27.84	246754
Vanier	CA		45.44	-75.66	17000
Vanier	CA		43.43	-80.45	15249
Vaniyambadi	IN		12.68	78.62	95061
Vannes	FR		47.66	-2.76	54020
Vantaa	FI		60.29	25.04	252724
Vapi	IN		20.37	72.90	163630
Varanasi	IN		25.32	83.01	1164404
Varennes	CA		45.68	-73.43	20994
Varese	IT		45.82	8.83	80588
Vargem Grande Paulista	BR		-23.60	-47.03	50415
Varginha	BR		-21.55	-45.43	136467
Varna	BG		43.22	27.91	318737
Varāmīn	IR		35.32	51.65	225628
Vasastaden	SE		59.35	18.03	58458
Vasco da Gama	IN		15.40	73.82	100485
Vaslui	RO		46.63	27.73	63035
Vasyl'evsky Ostrov	RU		59.94	30.25	203058
Vatican City	VA		41.90	12.45	829
Vatutino	RU		55.88	37.69	50000
Vaudreuil-Dorion	CA		45.40	-74.03	25789
Vaughan	CA		43.84	-79.50	323103
Vavoua	CI		7.38	-6.48	86977
Vavuniya	LK		8.75	80.50	60176
Vazhakkala	IN		10.01	76.33	51242
Vedado	CU		23.14	-82.39	108369
Vedado del Cotorro	CU		23.05	-82.25	74650
Vedder Crossing	CA		49.10	-121.97	22620
Veenendaal	NL		52.03	5.56	61271
Vejalpur	IN		22.69	73.56	121610
Vejle	DK		55.71	9.54	60231
Velampālaiyam	IN		11.14	77.31	87427
Velbert	DE		51.34	7.04	87669
Veles	MK		41.72	21.77	57873
Velikiy Novgorod	RU		58.52	31.27	222868
Velikiye Luki	RU		56.34	30.54	103149
Veliko Tŭrnovo	BG		43.08	25.63	59166
Velletri	IT		41.69	12.78	52911
Vellore	IN		12.92	79.13	484690
Velsen-Zuid	NL		52.46	4.65	67758
Venado Tuerto	AR		-33.75	-61.97	72340
Venice	IT		45.44	12.33	51298
Venice	US	California	33.99	-118.46	40885
Venice	US	Florida	27.10	-82.45	22211
Venkatagiri	IN		13.96	79.58	52688
Venlo	NL		51.37	6.17	101988
Ventas	ES		40.42	-3.65	50218
Ventura	US	California	34.28	-119.29	96769
Venustiano Carranza	MX		19.44	-99.10	430978
Venâncio Aires	BR		-29.61	-52.19	68763
Veracruz	MX		19.18	-96.14	428323
Verdun	CA		45.46	-73.57	69229
Vereeniging	ZA		-26.67	27.93	474681
Verhunskyi	UA		48.59	39.37	185593
Verkhnyaya Pyshma	RU		56.97	60.58	59061
Vermont Square	US	California	34.00	-118.30	47555
Vernon	CA		50.27	-119.27	40116
Vernon Hills	US	Illinois	42.22	-87.98	26314
Vero Beach	US	Florida	27.64	-80.40	16358
Vero Beach South	US	Florida	27.62	-80.41	23092
Verona	IT		45.44	10.99	258031
Versailles	FR		48.80	2.13	85416
Verviers	BE		50.59	5.86	52824
Verāval	IN		20.91	70.37	171121
Veshnyaki	RU		55.72	37.82	122000
Vespasiano	BR		-19.69	-43.92	129246
Vestal	US	New York	42.09	-76.05	28043
Vestavia Hills	US	Alabama	33.45	-86.79	34174
Veszprém	HU		47.09	17.91	56927
Viacha	BO		-16.65	-68.30	86218
Viamão	BR		-30.08	-51.02	285269
Viana	AO		-8.91	13.37	865863
Viana	BR		-20.39	-40.50	73423
Viana	BR		-3.22	-45.00	51442
Viareggio	IT		43.87	10.25	62169
Vicente Pires	BR		-15.81	-48.03	96871
Vicenza	IT		45.55	11.55	111980
Vicksburg	US	Mississippi	32.35	-90.88	23131
Victoria	HK		22.29	114.14	956800
Victoria	CA		48.44	-123.35	289625
Victoria	US	Texas	28.81	-97.00	67574
Victoria	PH		13.18	121.28	52215
Victoria	SC		-4.62	55.46	22881
Victoria de Durango	MX		24.02	-104.66	518709
Victoria Village	CA		43.73	-79.31	17510
Victoria-Downtown	CA		48.43	-123.36	46309
Victoria-Fraserview	CA		49.22	-123.07	31065
Victorias	PH		10.90	123.07	86510
Victoriaville	CA		46.05	-71.97	34426
Victorville	US	California	34.54	-117.29	122225
Vicálvaro	ES		40.40	-3.60	66439
Videira	BR		-27.01	-51.15	55466
Vidisha	IN		23.53	77.81	155951
Vidnoye	RU		55.55	37.71	51721
Vidradnyi	UA		50.43	30.42	69800
Vienna	AT		48.21	16.37	1691468
Vienna	US	Virginia	38.90	-77.27	16522
Vientiane	LA		17.97	102.60	840940
Viersen	DE		51.25	6.39	76153
Viewpark	GB		55.83	-4.06	16020
Vigevano	IT		45.31	8.85	57970
Vigia	BR		-0.86	-48.14	50832
Vigo	ES		42.23	-8.72	293642
Vihari	PK		30.04	72.36	112840
Vijalpor	IN		20.92	72.91	81245
Vijayapura	IN		16.82	75.72	327427
Vijayawada	IN		16.51	80.65	1143232
Vikindu	TZ		-7.01	39.30	70000
Vikārābād	IN		17.34	77.90	53143
Vila Andrade	BR		-23.63	-46.73	168669
Vila Curuca	BR		-23.51	-46.42	140673
Vila Flor	AO		-8.98	13.31	256066
Vila Formosa	BR		-23.57	-46.55	92186
Vila Guilherme	BR		-23.51	-46.61	52587
Vila Jacui	BR		-23.50	-46.46	134189
Vila Maria	BR		-23.51	-46.59	108543
Vila Mariana	BR		-23.59	-46.63	127286
Vila Matilde	BR		-23.54	-46.52	103558
Vila Medeiros	BR		-23.49	-46.58	114839
Vila Nova de Gaia	PT		41.12	-8.61	70811
Vila Prudente	BR		-23.59	-46.57	105590
Vila Velha	BR		-20.33	-40.29	394930
Vila-real	ES		39.94	-0.10	50577
Viladecans	ES		41.31	2.01	66168
Vilanova i la Geltrú	ES		41.22	1.73	65890
Vilhena	BR		-12.74	-60.15	95832
Viljoenskroon	ZA		-27.21	26.95	54955
Vilkhivskyi	UA		48.54	39.28	126340
Villa Alemana	CL		-33.05	-71.37	97320
Villa Bruzual	VE		9.33	-69.12	55244
Villa Canales	GT		14.48	-90.53	155423
Villa Carlos Paz	AR		-31.42	-64.49	69451
Villa de Cura	VE		10.04	-67.49	99669
Villa de Vallecas	ES		40.37	-3.60	65162
Villa del Rosario	CO		7.83	-72.47	64951
Villa Elisa	PY		-25.37	-57.59	64099
Villa Francisca	DO		18.48	-69.89	50185
Villa Hayes	PY		-25.09	-57.53	57217
Villa Lugano	AR		-34.68	-58.47	114000
Villa María	AR		-32.41	-63.24	92453
Villa Mercedes	CL		-37.40	-71.98	131936
Villa Mercedes	AR		-33.68	-65.46	96781
Villa Nueva	GT		14.53	-90.59	618397
Villa Park	US	Illinois	41.89	-87.99	21969
Villa Poeta José Gálvez Barrenechea	PE		-12.21	-76.91	61000
Villa Vicente Guerrero	MX		19.12	-98.17	60001
Villach	AT		46.61	13.86	58882
Villahermosa	MX		17.99	-92.94	353577
Villasis	PH		15.90	120.59	65086
Villaverde	ES		40.35	-3.70	126802
Villavicencio	CO		4.13	-73.63	321717
Ville-Marie	CA		45.50	-73.57	104944
Ville-Émard	CA		45.45	-73.60	30440
Villeneuve-d'Ascq	FR		50.62	3.17	62400
Villeray–Saint-Michel–Parc-Extension	CA		45.56	-73.61	144814
Villeurbanne	FR		45.77	4.88	131445
Villingen-Schwenningen	DE		48.06	8.49	81770
Villupuram	IN		11.94	79.49	97380
Vilnius	LT		54.69	25.28	542366
Vincennes	US	Indiana	38.68	-87.53	18012
Vincent	US	California	34.50	-118.12	15922
Vincent	US	California	34.10	-117.92	15922
Vincentown	US	New Jersey	39.93	-74.75	24664
Vineland	US	New Jersey	39.49	-75.03	60818
Vineyard	US	California	38.46	-121.35	24836
Vinh	VN		18.67	105.69	790000
Vinhedo	BR		-23.03	-46.98	80111
Vinhomes Ocean Park	VN		20.99	105.95	60000
Vinhomes Smart City	VN		21.00	105.74	50000
Vinhomes Times City	VN		20.99	105.87	50000
Vinnytsya	UA		49.23	28.47	430091
Vinto	BO		-17.39	-66.32	58739
Vinukonda	IN		16.05	79.74	62550
Virac	PH		13.58	124.24	75135
Viramgām	IN		23.13	72.05	55821
Viranşehir	TR		37.22	39.76	154163
Virginia	ZA		-28.10	26.87	122502
Virginia Beach	US	Virginia	36.85	-75.98	454808
Virudhachalam	IN		11.51	79.33	73585
Virudunagar	IN		9.59	77.96	73273
Virār	IN		19.46	72.81	1222390
Visakhapatnam	IN		17.68	83.20	1063178
Visalia	US	California	36.33	-119.29	130104
Viseu	PT		40.66	-7.91	103502
Viseu	BR		-1.20	-46.14	58692
Visitacion Valley	US	California	37.72	-122.40	22534
Visnagar	IN		23.70	72.55	76753
Vista	US	California	33.20	-117.24	100890
Vitebsk	BY		55.19	30.20	358927
Vitry-sur-Seine	FR		48.79	2.40	81001
Vittoria	IT		36.95	14.53	50852
Vitória	BR		-20.32	-40.34	312656
Vitória da Conquista	BR		-14.87	-40.84	253137
Vitória de Santo Antão	BR		-8.12	-35.29	134084
Vizianagaram	IN		18.12	83.41	228720
Viçosa	BR		-20.75	-42.88	76430
Viçosa do Ceará	BR		-3.56	-41.09	59712
Viña del Mar	CL		-33.02	-71.55	334248
Việt Trì	VN		21.32	105.40	415280
Việt Yên	VN		21.27	106.13	205900
Vlaardingen	NL		51.91	4.34	73798
Vladikavkaz	RU		43.04	44.67	306258
Vladimir	RU		56.14	40.40	357024
Vladivostok	RU		43.11	131.87	604901
Vlorë	AL		40.47	19.48	115261
Voi	KE		-3.40	38.56	53353
Volgodonsk	RU		47.51	42.15	167731
Volgograd	RU		48.71	44.50	1013533
Vologda	RU		59.22	39.88	312420
Volos	GR		39.37	22.95	86048
Volta Redonda	BR		-22.52	-44.10	279898
Volzhsk	RU		55.87	48.36	58000
Volzhsky	RU		48.79	44.78	323293
Vol’sk	RU		52.04	47.38	70500
Vorkuta	RU		67.51	64.07	80039
Voronezh	RU		51.67	39.19	1047549
Voskresenka	UA		50.48	30.60	84200
Voskresensk	RU		55.31	38.69	77086
Vostochnoe Degunino	RU		55.88	37.56	95000
Votkinsk	RU		57.05	53.99	98633
Votorantim	BR		-23.55	-47.44	127923
Votuporanga	BR		-20.42	-49.97	69863
Voznesenskyi	UA		47.93	37.63	85399
Vranje	RS		42.55	21.90	56199
Vriddhāchalam	IN		11.52	79.32	61498
Vrindāvan	IN		27.58	77.70	60195
Vryburg	ZA		-26.96	24.73	55879
Vryheid	ZA		-27.77	30.79	150012
Vwawa	TZ		-9.11	32.93	85000
Vyaz’ma	RU		55.21	34.30	55500
Vyborg	RU		60.71	28.75	78633
Vyhurivshchyna-Troyeshchyna	UA		50.51	30.60	240000
Vykhino-Zhulebino	RU		55.70	37.81	216000
Vyksa	RU		55.32	42.17	61664
Vynohradar	UA		50.51	30.42	57500
Vyshniy Volochëk	RU		57.59	34.57	53800
Várzea Grande	BR		-15.65	-56.13	314627
Várzea Paulista	BR		-23.21	-46.83	115771
Västerås	SE		59.62	16.55	127799
Växjö	SE		56.88	14.81	71282
Vélez-Málaga	ES		36.78	-4.10	74190
Vénissieux	FR		45.70	4.89	57584
Výronas	GR		37.96	23.75	61308
Vĩnh Châu	VN		9.32	105.98	183918
Vĩnh Long	VN		10.25	105.97	137870
Vĩnh Thạnh	VN		10.22	105.40	98399
Vĩnh Tuy	VN		21.00	105.88	86618
Vĩnh Yên	VN		21.31	105.60	119128
Vīrappanchathiram	IN		11.35	77.71	84453
Vīrapāndi	IN		11.06	77.35	50301
Vīrarāghavapuram	IN		13.07	80.11	64698
Vũng Tàu	VN		10.35	107.08	464860
Wa	GH		10.06	-2.50	78107
Wabu	KR		37.59	127.22	96775
Wacheng Neighborhood	CN		33.78	114.52	66848
Waco	US	Texas	31.55	-97.15	132356
Wad Medani	SD		14.40	33.52	332714
Wade Hampton	US	South Carolina	34.90	-82.33	20622
Wadgaon Kolhati	IN		19.84	75.24	65620
Wadsworth	US	Ohio	41.03	-81.73	21860
Wafangdian	CN		39.62	122.01	454338
Wah Cantt	PK		33.77	72.75	400733
Wahiawā	US	Hawaii	21.50	-158.02	17821
Wahiawā-Whitmore	US	Hawaii	21.51	-158.03	22448
Wahroonga	AU		-33.72	151.12	17652
Waiau-Pacific Palisades	US	Hawaii	21.40	-157.95	47591
Waiblingen	DE		48.83	9.32	52945
Waikīkī	US	Hawaii	21.29	-157.84	19862
Wailuku	US	Hawaii	20.89	-156.51	15313
Wainuiomata	NZ		-41.27	174.95	20450
Waipahu	US	Hawaii	21.39	-158.01	38216
Wajir	KE		1.75	40.06	90116
Wakayama	JP		34.23	135.17	356729
Wake Forest	US	North Carolina	35.98	-78.51	38199
Wakefield	GB		53.68	-1.50	109766
Wakefield	US	New York	40.90	-73.85	52201
Wakefield	US	Massachusetts	42.51	-71.07	24932
Wakiso	UG		0.40	32.46	87900
Wako	JP		35.79	139.62	83989
Waldorf	US	Maryland	38.62	-76.94	67752
Waliso	ET		8.53	37.97	78600
Walkden	GB		53.52	-2.40	35616
Walker	US	Michigan	43.00	-85.77	24647
Walla Walla	US	Washington	46.06	-118.34	32237
Wallan	AU		-37.42	144.98	15004
Wallasey	GB		53.42	-3.06	58794
Wallingford	US	Connecticut	41.46	-72.82	17712
Wallingford Center	US	Connecticut	41.45	-72.82	18209
Wallington	GB		51.36	-0.15	20850
Wallsend	GB		54.99	-1.53	42739
Walnut	US	California	34.02	-117.87	30237
Walnut Creek	US	California	37.91	-122.06	68910
Walnut Grove	CA		49.16	-122.64	25683
Walnut Park	US	California	33.97	-118.23	15966
Walsall	GB		52.59	-1.98	172141
Waltham	US	Massachusetts	42.38	-71.24	63378
Waltham Abbey	GB		51.69	-0.00	22858
Walthamstow	GB		51.59	-0.02	109424
Walton-on-Thames	GB		51.39	-0.41	22834
Walton-on-the-Naze	GB		51.85	1.27	17458
Walvis Bay	NA		-22.96	14.51	73598
Wamena	ID		-4.10	138.95	66080
Wan Chai	HK		22.28	114.17	166695
Wanchaq	PE		-13.52	-71.97	59134
Wandsbek	DE		53.58	10.08	411422
Wang Thonglang	TH		13.79	100.61	114768
Wangaratta	AU		-36.36	146.32	29808
Wanggou	CN		34.67	116.49	67140
Wangji	CN		33.98	117.75	54578
Wangkui	CN		46.83	126.48	99617
Wangqing	CN		43.31	129.76	88732
Wangsa Maju	MY		3.20	101.74	215600
Wanguru	KE		-0.68	37.36	51722
Wani	IN		20.06	78.95	58840
Wanju	KR		35.85	127.15	84009
Wanning	CN		18.80	110.38	545992
Wanparti	IN		16.37	78.07	60949
Wansheng	CN		28.96	106.93	113751
Wantagh	US	New York	40.68	-73.51	18871
Wantirna South	AU		-37.88	145.22	20754
Wanxian	CN		30.82	108.37	859662
Wanzhou	CN		30.76	108.40	1545900
Warabi	JP		35.82	139.69	75614
Warangal	IN		18.00	79.58	704570
Warder	ET		6.97	45.34	450400
Wardha	IN		20.74	78.60	113759
Ware	GB		51.81	-0.03	17576
Warminster	GB		51.20	-2.18	17490
Warner Robins	US	Georgia	32.62	-83.63	73490
Warragul	AU		-38.16	145.93	19856
Warren	US	Michigan	42.49	-83.01	134056
Warren	US	Ohio	41.24	-80.82	40245
Warren Township	US	New Jersey	40.61	-74.52	15311
Warrensburg	US	Missouri	38.76	-93.74	19927
Warri	NG		5.52	5.75	910000
Warrington	GB		53.39	-2.58	172330
Warrnambool	AU		-38.38	142.49	32894
Warsaw	PL		52.23	21.01	1702139
Warwick	US	Rhode Island	41.70	-71.42	81699
Warwick	GB		52.28	-1.58	37267
Warwick	AU		-28.22	152.03	15380
Warīsān	AE		25.17	55.41	108759
Wasaga Beach	CA		44.52	-80.02	20675
Wasco	US	California	35.59	-119.34	26279
Wasco	US	Illinois	41.94	-88.40	22560
Washington	US	District of Columbia	38.90	-77.04	689545
Washington	GB		54.90	-1.52	67085
Washington	US	Utah	37.13	-113.51	24299
Washington	US	Illinois	40.70	-89.41	16664
Washington Heights	US	New York	40.85	-73.94	152613
Washougal	US	Washington	45.58	-122.35	15288
Washwood Heath	GB		52.50	-1.83	32921
Wat Tha Phra	TH		13.73	100.48	53111
Watampone	ID		-4.54	120.33	149336
Watauga	US	Texas	32.86	-97.25	24525
Waterbury	US	Connecticut	41.56	-73.05	108802
Waterdown	CA		43.33	-79.88	24400
Waterford	US	Michigan	42.69	-83.41	75737
Waterford	IE		52.26	-7.11	60079
Waterford	US	Connecticut	41.34	-72.14	19281
Waterfront Communities-The Island	CA		43.63	-79.38	65913
Waterloo	CA		43.47	-80.52	104986
Waterloo	US	Iowa	42.49	-92.34	68460
Waterloo	SL		8.34	-13.07	55000
Waterlooville	GB		50.88	-1.03	64350
Watertown	US	Massachusetts	42.37	-71.18	31915
Watertown	US	New York	43.97	-75.91	26780
Watertown	US	Wisconsin	43.19	-88.73	23819
Watertown	US	South Dakota	44.90	-97.12	22073
Waterville	US	Maine	44.55	-69.63	16261
Watford	GB		51.66	-0.40	125707
Wath upon Dearne	GB		53.50	-1.35	16964
Watsonville	US	California	36.91	-121.76	53628
Wattenscheid	DE		51.48	7.14	73965
Watthana	TH		13.73	100.59	171150
Wau	SS		7.70	27.99	127384
Waukee	US	Iowa	41.61	-93.89	18990
Waukegan	US	Illinois	42.36	-87.84	88475
Waukesha	US	Wisconsin	43.01	-88.23	71970
Wausau	US	Wisconsin	44.96	-89.63	39094
Wauwatosa	US	Wisconsin	43.05	-88.01	47614
Waverly	US	Michigan	42.74	-84.62	23925
Wawer	PL		52.20	21.18	77205
Waxahachie	US	Texas	32.39	-96.85	33384
Wayaobu	CN		37.14	109.66	113698
Wayne	US	New Jersey	40.93	-74.28	57915
Wayne	US	Pennsylvania	40.04	-75.39	30892
Wayne	US	Michigan	42.28	-83.39	17081
Waynesboro	US	Virginia	38.07	-78.89	21491
Wazirabad	PK		32.44	74.12	152624
Wałbrzych	PL		50.77	16.28	127431
Wealdstone	GB		51.60	-0.34	18500
Weatherford	US	Texas	32.76	-97.80	28742
Webster Groves	US	Missouri	38.59	-90.36	23177
Wedding	DE		52.55	13.36	85275
Wedi	ID		-7.74	110.58	55300
Wednesbury	GB		52.55	-2.02	20313
Wednesfield	GB		52.60	-2.09	33555
Weifang	CN		36.71	119.10	2044028
Weihai	CN		37.51	122.11	844310
Weimar	DE		50.98	11.33	64727
Weimiao	CN		34.58	117.07	51820
Weinan	CN		34.50	109.51	1199290
Weining	CN		26.85	104.23	56744
Weirton	US	West Virginia	40.42	-80.59	19175
Weirton Heights	US	West Virginia	40.41	-80.54	19450
Wekiwa Springs	US	Florida	28.70	-81.43	21998
Weldiya	ET		11.83	39.59	104000
Weleri	ID		-6.97	110.07	58448
Welkom	ZA		-27.98	26.74	431944
Welk’īt’ē	ET		8.28	37.78	77500
Welland	CA		42.98	-79.25	52293
Wellesley	US	Massachusetts	42.30	-71.29	27982
Welling	GB		51.46	0.11	41000
Wellingborough	GB		52.30	-0.69	56564
Wellington	NZ		-41.29	174.78	381900
Wellington	US	Florida	26.66	-80.24	62560
Wellington	ZA		-33.64	19.01	55543
Wellington	GB		52.70	-2.52	22816
Welwyn Garden City	GB		51.80	-0.21	51505
Wembley	GB		51.55	-0.30	90045
Wenatchee	US	Washington	47.42	-120.31	33636
Wenchang	CN		19.55	110.80	560894
Wendo	ET		6.60	38.42	59300
Wenjiang	CN		28.39	104.56	68433
Wenling	CN		28.38	121.38	67433
Wenshan City	CN		23.36	104.25	450000
Wenshang	CN		35.73	116.50	59455
Wensu	CN		41.28	80.24	83110
Wentzville	US	Missouri	38.81	-90.85	35603
Wenxing	CN		28.68	112.88	57117
Wenzhou	CN		28.00	120.67	2650000
Werribee	AU		-37.90	144.67	50027
Weru	ID		-6.71	108.50	139004
Wesel	DE		51.67	6.62	61685
Weslaco	US	Texas	26.16	-97.99	39474
Wesley Chapel	US	Florida	28.24	-82.33	44092
West Albany	US	New York	42.68	-73.78	93794
West Allis	US	Wisconsin	43.02	-88.01	60620
West and East Lealman	US	Florida	27.82	-82.69	21924
West Babylon	US	New York	40.72	-73.35	43213
West Bend	US	Wisconsin	43.43	-88.18	31695
West Bloomfield Township	US	Michigan	42.57	-83.38	64690
West Bridgford	GB		52.93	-1.13	36487
West Bromwich	GB		52.52	-1.99	103112
West Carson	US	California	33.82	-118.29	21699
West Chester	US	Pennsylvania	39.96	-75.61	19842
West Chicago	US	Illinois	41.88	-88.20	27447
West Columbia	US	South Carolina	33.99	-81.07	16060
West Coon Rapids	US	Minnesota	45.16	-93.35	62528
West Covina	US	California	34.07	-117.94	108484
West Des Moines	US	Iowa	41.58	-93.71	64113
West Ealing	GB		51.51	-0.32	15169
West Elkridge	US	Maryland	39.21	-76.73	28734
West Elsdon	US	Illinois	41.79	-87.72	19219
West End	CA		49.28	-123.13	47200
West Englewood	US	Illinois	41.78	-87.67	32156
West Falls Church	US	Virginia	38.86	-77.19	29207
West Fargo	US	North Dakota	46.87	-96.90	33597
West Garfield Park	US	Illinois	41.88	-87.73	17742
West Gulfport	US	Mississippi	30.40	-89.09	71329
West Ham	GB		51.53	0.02	15551
West Hartford	US	Connecticut	41.76	-72.74	63268
West Haven	US	Connecticut	41.27	-72.95	54927
West Hempstead	US	New York	40.70	-73.65	18862
West Hill	CA		43.77	-79.18	27392
West Hills	US	California	34.20	-118.64	41426
West Hollywood	US	Florida	26.02	-80.18	60806
West Hollywood	US	California	34.09	-118.36	36222
West Humber-Clairville	CA		43.72	-79.60	33312
West Island	CC		-12.16	96.82	120
West Islip	US	New York	40.71	-73.31	28335
West Jerusalem	IL		31.78	35.22	400000
West Jordan	US	Utah	40.61	-111.94	111946
West Kelowna	CA		49.86	-119.58	28793
West Lafayette	US	Indiana	40.43	-86.91	45550
West Lake Sammamish	US	Washington	47.58	-122.10	33929
West Lake Stevens	US	Washington	47.99	-122.10	21047
West Lawn	US	Illinois	41.77	-87.72	32749
West Linn	US	Oregon	45.37	-122.61	26593
West Little River	US	Florida	25.86	-80.24	34699
West Lynchburg	US	Virginia	37.40	-79.18	65517
West Melbourne	US	Florida	28.07	-80.65	20679
West Memphis	US	Arkansas	35.15	-90.18	25052
West Mifflin	US	Pennsylvania	40.36	-79.87	20075
West Milford	US	New Jersey	41.13	-74.37	26968
West Molesey	GB		51.40	-0.38	18565
West New York	US	New Jersey	40.79	-74.01	53366
West Oak Lane	US	Pennsylvania	40.07	-75.17	38699
West Odessa	US	Texas	31.84	-102.50	22707
West Orange	US	New Jersey	40.80	-74.24	48131
West Palm Beach	US	Florida	26.72	-80.05	120932
West Park	US	Florida	25.98	-80.20	15097
West Pennant Hills	AU		-33.75	151.05	16162
West Pensacola	US	Florida	30.43	-87.28	21339
West Puente Valley	US	California	34.05	-117.97	22636
West Raleigh	US	North Carolina	35.79	-78.66	338759
West Ridge	US	Illinois	42.00	-87.69	72211
West Roxbury	US	Massachusetts	42.28	-71.15	30442
West Sacramento	US	California	38.58	-121.53	52721
West Saint Paul	US	Minnesota	44.92	-93.10	19540
West Scarborough	US	Maine	43.57	-70.39	27706
West Seneca	US	New York	42.85	-78.80	44711
West Springfield	US	Massachusetts	42.11	-72.62	27912
West Springfield	US	Virginia	38.77	-77.22	22460
West Torrington	US	Connecticut	41.82	-73.14	36000
West Town	US	Illinois	41.89	-87.67	86429
West University Place	US	Texas	29.72	-95.43	15741
West Valley City	US	Utah	40.69	-112.00	136208
West Vancouver	CA		49.33	-123.16	45487
West Village	US	New York	40.73	-74.01	32518
West Warwick	US	Rhode Island	41.70	-71.52	30146
West Whittier-Los Nietos	US	California	33.98	-118.07	25540
Westbrook	US	Maine	43.68	-70.37	17978
Westbury	GB		51.26	-2.19	16989
Westbury	US	New York	40.76	-73.59	15379
Westchase	US	Florida	28.06	-82.61	21747
Westchester	US	Florida	25.75	-80.33	29862
Westchester	US	Illinois	41.85	-87.88	16729
Westerly	US	Rhode Island	41.38	-71.83	17936
Westerville	US	Ohio	40.13	-82.93	38384
Westfield	US	Massachusetts	42.13	-72.75	41690
Westfield	US	Indiana	40.04	-86.13	36738
Westfield	US	New Jersey	40.66	-74.35	30548
Westford	US	Massachusetts	42.58	-71.44	21587
Westhoughton	GB		53.55	-2.52	26260
Westlake	US	Ohio	41.46	-81.92	32428
Westland	US	Michigan	42.32	-83.40	82000
Westmead	AU		-33.80	150.99	17835
Westminster	US	Colorado	39.84	-105.04	116317
Westminster	US	California	33.76	-118.01	92114
Westminster	US	Maryland	39.58	-77.00	18670
Westminster-Branson	CA		43.78	-79.45	26274
Westmont	US	California	33.94	-118.30	31853
Westmont	US	Illinois	41.80	-87.98	24941
Westmount	CA		45.48	-73.60	20494
Weston	US	Florida	26.10	-80.40	69959
Weston	CA		43.70	-79.52	17992
Weston	US	Wisconsin	44.89	-89.55	15069
Weston-super-Mare	GB		51.35	-2.98	82903
Westonaria	ZA		-26.32	27.65	156831
Westpark	US	California	33.69	-117.81	22993
Westport	US	Connecticut	41.14	-73.36	26391
Westwood Plateau	CA		49.30	-122.79	19776
Wethersfield	US	Connecticut	41.71	-72.65	26668
Wetzlar	DE		50.56	8.50	52656
Wexford	IE		52.33	-6.46	21524
Wexford/Maryvale	CA		43.75	-79.30	27917
Weybridge	GB		51.37	-0.46	19463
Weymouth	US	Massachusetts	42.22	-70.94	54395
Weymouth	GB		50.61	-2.46	53416
Whakatane	NZ		-37.96	176.99	18602
Whalley	CA		49.18	-122.87	102555
Whanganui	NZ		-39.93	175.05	49200
Whangarei	NZ		-35.73	174.32	50900
Wharton	US	Pennsylvania	39.93	-75.16	49732
Wheat Ridge	US	Colorado	39.77	-105.08	31192
Wheaton	US	Illinois	41.87	-88.11	53715
Wheaton	US	Maryland	39.04	-77.06	48284
Wheelers Hill	AU		-37.90	145.18	20652
Wheeling	US	Illinois	42.14	-87.93	38079
Wheeling	US	West Virginia	40.06	-80.72	27648
Whickham	GB		54.95	-1.68	16625
Whitby	CA		43.88	-78.93	138501
Whitchurch-Stouffville	CA		44.00	-79.32	49864
White Bear Lake	US	Minnesota	45.08	-93.01	25205
White Oak	US	Ohio	39.21	-84.60	19167
White Oak	US	Maryland	39.04	-76.99	17403
White Plains	US	New York	41.03	-73.76	58459
White Rock	CA		49.02	-122.80	23670
White Settlement	US	Texas	32.76	-97.46	17077
Whitefield	GB		53.55	-2.30	23545
Whitehall	US	Ohio	39.97	-82.89	18694
Whitehall Township	US	Pennsylvania	40.67	-75.50	24896
Whitehaven	GB		54.55	-3.58	22945
Whitehorse	CA		60.72	-135.05	28201
Whitestone	US	New York	40.79	-73.82	36984
Whitley Bay	GB		55.04	-1.45	38055
Whitman	US	Pennsylvania	39.92	-75.16	49732
Whitney	US	Nevada	36.10	-115.04	38585
Whitstable	GB		51.36	1.03	32196
Whittier	US	California	33.98	-118.03	87438
Whyalla	AU		-33.03	137.56	20880
Wichita	US	Kansas	37.69	-97.34	396119
Wichita Falls	US	Texas	33.91	-98.49	104710
Wickford	GB		51.61	0.52	27535
Widnes	GB		53.36	-2.73	61464
Wiesbaden	DE		50.09	8.24	288850
Wigan	GB		53.54	-2.64	175405
Wigston Magna	GB		52.58	-1.09	37260
Wik’ro	ET		13.80	39.60	64000
Wildomar	US	California	33.60	-117.28	35632
Wildwood	US	Missouri	38.58	-90.66	35899
Wilhelmsburg	DE		53.49	10.01	53064
Wilhelmshaven	DE		53.55	8.10	84393
Wilkes-Barre	US	Pennsylvania	41.25	-75.88	40780
Wilkinsburg	US	Pennsylvania	40.44	-79.88	15731
Willemstad	CW		12.12	-68.89	125000
Willenhall	GB		52.59	-2.06	49587
Willesden	GB		51.53	-0.23	44295
Willetton	AU		-32.05	115.89	19262
Williamsburg	US	New York	40.71	-73.95	33000
Williamsburg	US	Virginia	37.27	-76.71	15052
Williamsport	US	Pennsylvania	41.24	-77.00	29201
Williamstown	US	New Jersey	39.69	-75.00	15567
Willich	DE		51.26	6.55	51843
Willimantic	US	Connecticut	41.71	-72.21	17737
Willingboro	US	New Jersey	40.03	-74.87	31668
Williston	US	North Dakota	48.15	-103.62	26977
Willmar	US	Minnesota	45.12	-95.04	19638
Willoughby	CA		49.13	-122.68	31305
Willoughby	US	Ohio	41.64	-81.41	22631
Willow Grove	US	Pennsylvania	40.14	-75.12	15726
Willowbrook	US	California	33.92	-118.26	35983
Willowdale	CA		43.77	-79.40	79440
Willowdale East	CA		43.77	-79.40	50434
Willowdale West	CA		43.77	-79.43	16936
Willowridge-Martingrove-Richview	CA		43.68	-79.55	22156
Wilmersdorf	DE		52.48	13.32	101877
Wilmette	US	Illinois	42.07	-87.72	27413
Wilmington	US	North Carolina	34.24	-77.95	115933
Wilmington	US	Delaware	39.75	-75.55	70898
Wilmington	US	California	33.78	-118.26	52000
Wilmington	US	Massachusetts	42.55	-71.17	22325
Wilmington Island	US	Georgia	32.00	-80.97	15138
Wilmslow	GB		53.33	-2.23	25725
Wilson	US	North Carolina	35.72	-77.92	49643
Wilsonville	US	Oregon	45.30	-122.77	22729
Wilton	US	Connecticut	41.20	-73.44	18062
Wilton	US	New York	43.18	-73.74	17361
Wimbledon	GB		51.42	-0.21	68187
Wimborne Minster	GB		50.78	-1.98	15552
Winchester	GB		51.07	-1.32	46074
Winchester	US	Nevada	36.13	-115.12	27978
Winchester	US	Virginia	39.19	-78.16	27284
Winchester	US	Massachusetts	42.45	-71.14	21374
Winchester	US	Kentucky	37.99	-84.18	18446
Winder	US	Georgia	33.99	-83.72	15447
Windham	US	Connecticut	41.70	-72.16	23072
Windhoek	NA		-22.56	17.08	386219
Windsor	CA		42.30	-83.02	229660
Windsor	US	Colorado	40.48	-104.90	32716
Windsor	GB		51.48	-0.60	31560
Windsor	US	Connecticut	41.85	-72.64	28778
Windsor	US	California	38.55	-122.82	27464
Winejok	SS		9.01	27.57	300000
Winneba	GH		5.35	-0.62	71288
Winnetka	US	California	34.21	-118.57	47000
Winnipeg	CA		49.88	-97.15	749607
Winona	US	Minnesota	44.05	-91.64	27094
Winsford	GB		53.19	-2.52	30259
Winston-Salem	US	North Carolina	36.10	-80.24	241218
Winter Garden	US	Florida	28.57	-81.59	40356
Winter Gardens	US	California	32.83	-116.93	20631
Winter Haven	US	Florida	28.02	-81.73	37689
Winter Park	US	Florida	28.60	-81.34	29943
Winter Springs	US	Florida	28.70	-81.31	34789
Winterhude	DE		53.59	10.01	56382
Winterthur	CH		47.51	8.72	111840
Winthrop	US	Massachusetts	42.38	-70.98	17618
Wisbech	GB		52.67	0.16	32489
Wisconsin Rapids	US	Wisconsin	44.38	-89.82	17897
Wishaw	GB		55.77	-3.92	30050
Wissinoming	US	Pennsylvania	40.02	-75.06	21445
Witham	GB		51.80	0.64	25353
Witney	GB		51.78	-1.49	29103
Witten	DE		51.44	7.35	91808
Woburn	CA		43.77	-79.23	53485
Woburn	US	Massachusetts	42.48	-71.15	39555
Wodonga	AU		-36.12	146.89	38949
Wokha	IN		26.10	94.26	54010
Woking	GB		51.32	-0.56	103900
Wokingham	GB		51.41	-0.84	41143
Wola	PL		52.23	20.96	140958
Wolcott	US	Connecticut	41.60	-72.99	16639
Wolf Trap	US	Virginia	38.94	-77.29	16131
Wolfenbüttel	DE		52.16	10.54	54740
Wolfsburg	DE		52.42	10.78	123064
Wollert	AU		-37.58	145.03	24407
Wollongong	AU		-34.42	150.89	280153
Wollongong city centre	AU		-34.43	150.89	19108
Woluwe-Saint-Lambert	BE		50.84	4.43	56584
Wolverhampton	GB		52.59	-2.12	263700
Wombwell	GB		53.52	-1.40	15518
Wong Tai Sin	HK		22.35	114.18	425235
Wonosari	ID		-7.97	110.60	87454
Wonosobo	ID		-7.36	109.90	92990
Wood Green	GB		51.60	-0.12	28453
Woodbridge	US	California	33.68	-117.79	24966
Woodbridge	US	New Jersey	40.56	-74.28	19265
Woodburn	US	Oregon	45.14	-122.86	25173
Woodbury	US	Minnesota	44.92	-92.96	67855
Woodford Green	GB		51.61	0.02	22803
Woodhaven	US	New York	40.69	-73.86	36555
Woodland	US	California	38.68	-121.77	58567
Woodland Hills	US	California	34.17	-118.61	70000
Woodlands	SG		1.44	103.79	254440
Woodlawn	US	Maryland	39.32	-76.73	37879
Woodlawn	US	Illinois	41.78	-87.60	24150
Woodlawn	US	Virginia	38.72	-77.13	20804
Woodlawn	CA		44.68	-63.53	20000
Woodmere	US	New York	40.63	-73.71	17121
Woodridge	US	Illinois	41.75	-88.05	33370
Woodrow	US	New York	40.54	-74.19	21005
Woodside	US	New York	40.75	-73.91	41981
Woodstock	CA		43.13	-80.75	40404
Woodstock	US	Georgia	34.10	-84.52	29898
Woodstock	US	Illinois	42.31	-88.45	25189
Woonsocket	US	Rhode Island	42.00	-71.51	41475
Wooster	US	Ohio	40.81	-81.94	26749
Worcester	US	Massachusetts	42.26	-71.80	206518
Worcester	ZA		-33.65	19.45	127597
Worcester	GB		52.19	-2.22	101659
Worcester Park	GB		51.38	-0.24	16031
Workington	GB		54.64	-3.54	21275
Worksop	GB		53.30	-1.12	44733
Worms	DE		49.63	8.36	81099
Worthing	GB		50.82	-0.38	113866
Wrexham	GB		53.05	-2.99	65692
Wright	US	Florida	30.46	-86.64	23127
Wrocław	PL		51.10	17.03	672545
Wrzeszcz	PL		54.38	18.61	65000
Wuchang	CN		44.93	127.16	94786
Wucheng	CN		29.60	118.17	60212
Wuchuan	CN		21.46	110.77	104168
Wuda	CN		39.50	106.71	129922
Wufeng	TW		24.06	120.70	65567
Wugang	CN		26.73	110.63	132457
Wuhai	CN		39.68	106.82	218427
Wuhan	CN		30.58	114.27	10392693
Wuhu	CN		31.35	118.43	1598165
Wujiaqu	CN		44.16	87.52	154400
Wujing	CN		36.45	118.40	60260
Wukari	NG		7.87	9.78	92933
Wulingyuan	CN		29.35	110.54	52712
Wulong	CN		29.32	107.76	78225
Wuppertal	DE		51.26	7.15	360797
Wushan	CN		31.08	109.88	117873
Wushan	CN		34.72	104.89	68643
Wusu	CN		44.43	84.68	72587
Wuwei	CN		37.93	102.63	1010295
Wuxi	CN		31.57	120.29	4396835
Wuxi	CN		26.58	111.86	66442
Wuxue	CN		29.85	115.55	220661
Wuyang	CN		31.99	116.25	79070
Wuyishan	CN		27.76	118.03	137133
Wuzhen	CN		30.75	120.49	60000
Wuzhishan	CN		18.78	109.50	112269
Wuzhong	CN		37.99	106.20	7202654
Wuzhou	CN		23.48	111.29	761948
Wyandotte	US	Michigan	42.21	-83.15	25156
Wyckoff	US	New Jersey	41.01	-74.17	17124
Wylie	US	Texas	33.02	-96.54	46708
Wyndham Vale	AU		-37.89	144.62	20518
Wyoming	US	Michigan	42.91	-85.71	75275
Währing	AT		48.23	16.34	51402
Wîhkwêntôwin	CA		53.54	-113.52	18180
Würzburg	DE		49.79	9.95	133731
Wādī as Sīr	JO		31.95	35.82	181212
Wāri	IN		21.15	79.01	54048
Wāshīm	IN		20.11	77.13	78387
Włocławek	PL		52.65	19.07	120339
Wŏnju	KR		37.35	127.95	332849
Wŏnsan	KP		39.15	127.44	329207
Xai-Xai	MZ		-25.05	33.64	154356
Xalapa de Enríquez	MX		19.53	-96.92	424755
Xam Nua	LA		20.42	104.05	56900
Xanxerê	BR		-26.88	-52.40	51607
Xaçmaz	AZ		41.46	48.81	67600
Xenia	US	Ohio	39.68	-83.93	25976
Xiamen	CN		24.48	118.08	4617251
Xiangcheng	CN		25.47	100.56	121959
Xiangcheng	CN		33.85	113.49	65833
Xiangtan	CN		27.85	112.90	959303
Xiangxiang	CN		27.73	112.53	87592
Xiangyang	CN		32.04	112.14	1294733
Xiangzhou	CN		36.16	119.42	61748
Xianju	CN		28.85	120.73	61532
Xianning	CN		29.84	114.32	512517
Xiannü	CN		32.43	119.56	83936
Xianshuigu	CN		38.98	117.38	74028
Xiantao	CN		30.37	113.44	239406
Xianyang	CN		34.34	108.70	1034081
Xiaogan	CN		30.93	113.92	908266
Xiaolingwei	CN		32.03	118.85	66031
Xiaoshan	CN		30.17	120.26	95234
Xiaoshi	CN		41.30	124.12	68994
Xiaoweizhai	CN		26.19	107.51	58913
Xiayang	CN		31.15	121.12	137321
Xiazhen	CN		34.80	117.11	125667
Xiazhuang	CN		36.45	119.84	88710
Xiazhuang	CN		34.92	118.64	63285
Xiazhuang	CN		25.40	100.83	53954
Xichang	CN		27.90	102.26	481796
Xichang	CN		21.63	108.95	80064
Xico	MX		19.27	-98.95	384327
Xiema	CN		29.77	106.37	60933
Xifeng	CN		42.74	124.72	61087
Xigang	CN		38.55	106.35	112061
Xihe	CN		31.69	113.47	90422
Xihu	TW		23.96	120.48	54033
Xilin Hot	CN		43.97	116.03	120965
Xilinhot	CN		43.94	116.07	349953
Ximeicun	CN		24.99	118.39	94326
Xincheng	CN		41.71	82.93	102752
Xincheng	CN		33.63	115.18	65411
Xindi	CN		29.82	113.47	175761
Xindian	CN		36.80	118.29	82555
Xingcheng	CN		40.62	120.72	98968
Xingguo	CN		34.86	105.67	95211
Xinghua	CN		32.94	119.83	105918
Xinglongshan	CN		43.96	125.47	58432
Xingning	CN		24.15	115.72	274499
Xingqiao	CN		30.40	120.25	52400
Xingren	CN		25.43	105.23	91579
Xingtai	CN		37.06	114.49	798770
Xinguara	BR		-7.10	-49.94	52893
Xingyi	CN		25.10	104.91	322890
Xinhe	CN		36.92	119.59	69884
Xining	CN		36.63	101.76	1677177
Xininglu	CN		44.34	84.90	69361
Xinji	CN		37.93	115.22	145911
Xinle	CN		38.35	114.69	99347
Xinmin	CN		41.99	122.83	74139
Xinqiao	CN		31.07	121.31	155856
Xinqing	CN		48.29	129.52	55415
Xinshi	CN		31.05	113.14	98422
Xintai	CN		35.90	117.75	222459
Xinxiang	CN		35.19	113.80	1047088
Xinxing	CN		34.78	105.32	97483
Xinyang	CN		32.12	114.07	1230042
Xinye	CN		32.53	112.37	61633
Xinyi	CN		34.38	118.35	300511
Xinyi	CN		22.37	110.95	98259
Xinying	TW		23.31	120.31	74972
Xinyu	CN		27.80	114.93	839488
Xinyuan	CN		43.43	83.25	282718
Xinzhai	CN		36.40	118.62	100168
Xinzhi	CN		36.50	111.70	72303
Xinzhou	CN		38.41	112.73	544683
Xinzhou	CN		30.87	114.80	78767
Xinzhou	CN		19.71	109.31	67316
Xiongzhou	CN		25.12	114.30	79050
Xishan	CN		27.67	113.50	98162
Xiugu	CN		27.91	116.78	81153
Xiulin	CN		29.72	112.40	122411
Xiuyan	CN		40.29	123.27	71614
Xiuying	CN		20.00	110.29	290000
Xiva	UZ		41.39	60.36	115000
Xixiang	CN		32.99	107.76	99867
Xixiang	CN		22.59	113.89	78022
Xixiang	CN		35.16	112.86	60745
Xizhi	TW		25.07	121.66	204619
Xi’an	CN		34.26	108.93	9600000
Xochimilco	MX		19.25	-99.10	442178
Xo‘jayli Shahri	UZ		42.41	59.45	67800
Xuancheng	CN		30.95	118.76	774332
Xuanhua	CN		40.61	115.06	373422
Xuantan	CN		29.21	105.57	69250
Xuchang	CN		34.03	113.86	1265536
Xucheng	CN		20.33	110.17	83267
Xuhui	CN		31.20	121.45	1109800
Xujiang	CN		26.84	116.32	87459
Xunchang	CN		28.45	104.71	118664
Xunyang	CN		32.82	109.37	67929
Xuyong	CN		28.17	105.43	108352
Xuzhou	CN		34.20	117.28	1253991
Xuzhuang	CN		34.30	117.46	56099
Xuân Lộc	VN		10.93	107.23	253140
Xóm Cái Nước	VN		9.80	105.10	54397
Ya'an	CN		29.99	103.00	612056
Yachimata	JP		35.65	140.32	68769
Yachiyo	JP		35.74	140.12	199498
Yacuiba	BO		-22.02	-63.68	82803
Yadgir	IN		16.77	77.14	74294
Yagoona	AU		-33.90	151.02	17908
Yagoua	CM		10.34	15.23	59069
Yaizu	JP		34.87	138.32	139578
Yakeshi	CN		49.28	120.73	116284
Yakima	US	Washington	46.60	-120.51	93701
Yakutsk	RU		62.03	129.72	235600
Yala	TH		6.54	101.28	93558
Yalova	TR		40.66	29.28	71289
Yalta	UA		44.50	34.17	77003
Yamagata	JP		38.23	140.37	248772
Yamaguchi	JP		34.18	131.47	193966
Yamato	JP		35.47	139.45	242065
Yamato-Takada	JP		34.52	135.75	61744
Yamatokōriyama	JP		34.61	135.77	83285
Yambol	BG		42.48	26.50	63656
Yame	JP		33.23	130.65	60608
Yamethin	MM		20.43	96.14	59867
Yamoussoukro	CI		6.82	-5.28	275686
Yamuna Nagar	IN		30.13	77.28	217071
Yan Besar	MY		5.80	100.37	67653
Yan Nawa	TH		13.70	100.54	81521
Yanagawa	JP		33.17	130.40	64475
Yanam	IN		16.73	82.21	55626
Yanbu	SA		24.09	38.06	200161
Yancheng	CN		33.36	120.16	1615717
Yangambi	CD		0.77	24.44	62082
Yangcheng	CN		30.00	106.26	186242
Yangchun	CN		22.17	111.78	153547
Yangcun	CN		39.36	117.06	63756
Yanggu	CN		36.11	115.78	74725
Yanghang	CN		31.37	121.44	204564
Yanghe	CN		38.28	106.25	67901
Yanghe	CN		36.14	119.91	50371
Yangiyŭl	UZ		41.11	69.05	61700
Yangjiang	CN		21.86	111.96	1292987
Yangju	KR		37.83	127.06	179923
Yangliuqing	CN		39.14	117.00	76387
Yangon	MM		16.81	96.16	4477638
Yangp'yŏng	KR		37.49	127.49	83367
Yangpu	CN		31.26	121.52	1210800
Yangquan	CN		37.86	113.56	731228
Yangsan	KR		35.34	129.03	358074
Yangshuo	CN		24.78	110.49	300000
Yangtun	CN		34.88	116.88	53417
Yangzhou	CN		32.40	119.44	1584237
Yangzhou	CN		33.22	107.54	64349
Yanji	CN		42.89	129.50	326957
Yanjia	CN		29.83	107.00	72825
Yanliang	CN		34.66	109.23	60891
Yanta	CN		36.24	115.67	79196
Yantai	CN		37.48	121.44	2227733
Yantongshan	CN		43.29	126.01	57515
Yanzhou	CN		35.55	116.83	254788
Yan’an	CN		36.60	109.49	475234
Yao	JP		34.62	135.60	273213
Yaoji	CN		34.07	117.82	65897
Yaoundé	CM		3.87	11.52	1299369
Yaowan	CN		34.18	118.07	60668
Yaren	NR		-0.55	166.93	1100
Yaritagua	VE		10.08	-69.12	113343
Yarm	GB		54.50	-1.36	19184
Yarmouth	US	Massachusetts	41.71	-70.23	25243
Yaroslavl	RU		57.63	39.87	608722
Yaroslavskiy	RU		55.88	37.72	91000
Yarraville	AU		-37.82	144.90	15636
Yartsevo	RU		55.06	32.70	52706
Yasenevo	RU		55.61	37.52	180000
Yashan	CN		22.20	109.94	56629
Yashio	JP		35.82	139.84	93363
Yasu	JP		35.10	136.02	50695
Yasuj	IR		30.67	51.59	96786
Yate	GB		51.54	-2.42	23703
Yateley	GB		51.34	-0.83	20334
Yatou	CN		37.16	122.44	91517
Yautepec	MX		18.88	-99.07	105780
Yavatmāl	IN		20.39	78.13	128175
Yawata	JP		34.87	135.70	71656
Yawnghwe	MM		20.66	96.93	188083
Yaxing	CN		19.45	109.26	76427
Yazd	IR		31.90	54.37	477905
Yazman	PK		29.12	71.74	60738
Yeadon	GB		53.86	-1.69	37379
Yebaishou	CN		41.40	119.64	65536
Yecheon	KR		36.66	128.46	54873
Yegor’yevsk	RU		55.38	39.04	85200
Yei	SS		4.09	30.68	260720
Yekaterinburg	RU		56.86	60.62	1495066
Yelabuga	RU		55.76	52.04	72643
Yelahanka	IN		13.10	77.60	116447
Yelets	RU		52.61	38.51	115688
Yellowknife	CA		62.45	-114.37	20340
Yenagoa	NG		4.93	6.27	365000
Yenakiyeve	UA		48.24	38.20	76673
Yenangyaung	MM		20.47	94.87	110553
Yendi	GH		9.44	-0.01	64676
Yeoju	KR		37.30	127.63	111897
Yeongam	KR		34.80	126.70	51573
Yeonggwang	KR		35.28	126.51	51688
Yeongju	KR		36.82	128.63	84625
Yeosu	KR		34.76	127.66	268823
Yeovil	GB		50.94	-2.63	50176
Yerba Buena	AR		-26.81	-65.30	50783
Yerevan	AM		40.18	44.51	1144700
Yessentuki	RU		44.05	42.86	81015
Yevlakh	AZ		40.62	47.15	127400
Yevpatoriya	UA		45.20	33.37	107040
Yeysk	RU		46.69	38.28	87814
Yeyuan	CN		36.42	118.50	97936
Yezhou	CN		30.60	109.72	104839
Yibin	CN		28.76	104.64	836340
Yichang	CN		30.71	111.28	1350150
Yicheng	CN		31.70	112.26	61027
Yichun	CN		27.83	114.40	1045952
Yichun	CN		47.72	128.88	155762
Yidu	CN		36.77	118.42	105070
Yigou	CN		35.81	114.32	59073
Yilan	TW		24.76	121.75	94188
Yilan	CN		46.32	129.56	71180
Yima	CN		34.74	111.88	82509
Yinchuan	CN		38.47	106.27	1487579
Yingge	TW		24.96	121.35	87920
Yingjiang	CN		24.71	97.94	80481
Yingkou	CN		40.66	122.23	591159
Yingli	CN		37.06	118.81	57091
Yingqiu	CN		36.53	118.99	92564
Yingshang Chengguanzhen	CN		32.63	116.27	61771
Yingtan	CN		28.23	117.00	214229
Yinma	CN		36.66	119.46	83872
Yintai	CN		35.12	109.10	217509
Yinzhu	CN		35.88	119.98	75656
Yirga ‘Alem	ET		6.75	38.42	81600
Yishan	CN		36.22	118.70	78408
Yishui	CN		35.78	118.63	94115
Yishun New Town	SG		1.43	103.83	228730
Yiwu	CN		29.32	120.08	1481384
Yixing	CN		31.36	119.82	1285785
Yizhou	CN		24.50	108.67	155872
Yogyakarta	ID		-7.80	110.36	375699
Yokkaichi	JP		34.97	136.62	305424
Yokkaichi	JP		33.54	131.33	52771
Yokohama	JP		35.43	139.65	3777491
Yokosuka	JP		35.28	139.67	409478
Yokota	JP		35.75	139.38	69550
Yokote	JP		39.32	140.55	85555
Yola	NG		9.21	12.48	460000
Yonago	JP		35.43	133.33	148720
Yonezawa	JP		37.91	140.12	94486
Yongbei	CN		26.65	100.78	60099
Yongchuan	CN		29.35	105.89	192954
Yongfeng	CN		27.45	112.17	70783
Yongji	CN		34.87	110.44	452000
Yongjian	CN		25.43	100.21	53970
Yongkang	TW		23.02	120.26	233730
Yongning	CN		22.76	108.48	61690
Yongqing	CN		34.75	106.13	55595
Yongzhou	CN		26.42	111.61	1020715
Yong’an	CN		31.02	109.46	144314
Yonkers	US	New York	40.93	-73.90	201116
Yono	JP		35.88	139.63	102364
Yopal	CO		5.34	-72.39	168433
Yorba Linda	US	California	33.89	-117.81	67973
York	GB		53.96	-1.08	156135
York	US	Pennsylvania	39.96	-76.73	43992
York University Heights	CA		43.77	-79.49	27593
Yorkton	CA		51.22	-102.47	16343
Yorkville	US	Illinois	41.64	-88.45	18451
Yoshikawa	JP		35.89	139.84	73262
Yoshkar-Ola	RU		56.64	47.89	268272
Yotsukaidō	JP		35.65	140.17	95266
Yotsuya	JP		35.69	139.72	74800
Youhao	CN		47.85	128.84	78402
Youkaichi	JP		35.12	136.20	112819
Youngstown	US	Ohio	41.10	-80.65	64628
Youssoufia	MA		32.25	-8.53	73848
Yousuo	CN		26.03	100.07	53233
Youxi	CN		29.21	106.14	63386
Yozgat	TR		39.82	34.80	87881
Ypsilanti	US	Michigan	42.24	-83.61	19945
Yuanlin	TW		23.96	120.58	124725
Yuanping	CN		38.72	112.76	82883
Yuanshang	CN		36.77	120.35	74253
Yuba City	US	California	39.14	-121.62	66941
Yucaipa	US	California	34.03	-117.04	53328
Yucca Valley	US	California	34.11	-116.43	21600
Yucheng	CN		34.93	116.47	62365
Yuci	CN		37.68	112.73	235929
Yudong	CN		29.39	106.52	81408
Yuen Long	HK		22.45	114.03	200000
Yuen Long Kau Hui	HK		22.45	114.03	169600
Yuen Long San Hui	HK		22.43	114.03	200000
Yuepu	CN		31.43	121.42	139328
Yueyang	CN		29.37	113.09	991465
Yukon	US	Oklahoma	35.51	-97.76	25892
Yuktae-dong	KP		40.02	128.16	76427
Yukuhashi	JP		33.73	130.98	71426
Yulin	CN		22.63	110.15	1056743
Yulinshi	CN		38.29	109.74	90870
Yuma	US	Arizona	32.73	-114.62	95548
Yumbo	CO		3.58	-76.49	71436
Yuncheng	CN		35.02	110.99	680036
Yunfu	CN		22.93	112.04	2612800
Yunjin	CN		29.08	105.64	54385
Yunlong	CN		34.25	117.25	345393
Yunmen	CN		30.08	106.32	68698
Yunmeng Chengguanzhen	CN		31.06	113.77	64390
Yunnanyi	CN		25.42	100.69	93671
Yunshan	CN		36.82	120.23	52249
Yunusobod	UZ		41.37	69.28	352000
Yunyang	CN		33.45	112.71	73922
Yurga	RU		55.72	84.89	84220
Yurihonjō	JP		39.39	140.06	76077
Yushu	CN		33.00	97.01	141308
Yushu	CN		44.83	126.54	124736
Yutan	CN		28.26	112.56	55312
Yuxi	CN		24.36	102.54	103829
Yuxia	CN		34.06	108.63	60206
Yuyao	CN		30.05	121.15	114177
Yuzhno-Sakhalinsk	RU		46.95	142.74	198973
Yuzhou	CN		34.15	113.47	87961
Yuzivskyi	UA		48.00	37.80	94228
Yên Bái	VN		21.72	104.91	100631
Yên Hòa	VN		21.02	105.79	77029
Yên Vinh	VN		18.67	105.67	107082
Yüksekova	TR		37.57	44.29	71729
Yūki	JP		36.30	139.88	50645
Zaandam	NL		52.44	4.83	71708
Zaanstad	NL		52.45	4.81	140085
Zabrze	PL		50.32	18.79	192177
Zabīd	YE		14.20	43.32	52590
Zacapa	GT		14.97	-89.53	60424
Zacapu	MX		19.82	-101.79	50112
Zacatecas	MX		22.77	-102.58	129011
Zachary	US	Louisiana	30.65	-91.16	16448
Zadar	HR		44.12	15.23	67309
Zagazig	EG		30.59	31.50	430445
Zagné	CI		6.21	-7.48	63341
Zagreb	HR		45.81	15.98	663592
Zahedan	IR		29.50	60.86	551980
Zahir Pir	PK		28.81	70.52	76979
Zahirābād	IN		17.68	77.61	71166
Zahlé	LB		33.85	35.90	78145
Zalaegerszeg	HU		46.84	16.84	61898
Zalău	RO		47.20	23.05	52359
Zama	JP		35.49	139.39	132325
Zamboanga	PH		6.91	122.07	1018849
Zamora	ES		41.51	-5.74	61827
Zamora de Hidalgo	MX		19.98	-102.29	186102
Zamoskvorech’ye	RU		55.73	37.63	55000
Zamość	PL		50.72	23.25	66034
Zanesville	US	Ohio	39.94	-82.01	25498
Zango	AO		-9.01	13.38	198538
Zanjan	IR		36.68	48.50	357471
Zanzibar	TZ		-6.16	39.20	709809
Zaoyang	CN		32.13	112.75	184509
Zaozhuang	CN		34.86	117.55	899753
Zapopan	MX		20.72	-103.39	1476491
Zaporizhzhya	UA		47.85	35.12	710052
Zaragoza	ES		41.66	-0.88	686986
Zaragoza	PH		15.45	120.80	53090
Zarand	IR		30.81	56.56	58983
Zaraza	VE		9.35	-65.32	74017
Zarechnyy	RU		53.20	45.19	63579
Zarechnyy	RU		53.13	46.58	62139
Zaria	NG		11.11	7.72	980000
Zarichnyi	UA		50.90	34.81	150694
Zarinsk	RU		53.71	84.94	52209
Zarqa	JO		32.07	36.09	792665
Zarrīn Shahr	IR		32.39	51.38	55817
Zarzis	TN		33.50	11.11	79316
Zawiercie	PL		50.49	19.42	53159
Zawiya	LY		32.75	12.73	186123
Zaxo	IQ		37.15	42.69	95052
Zayed City	AE		23.65	53.71	63482
Zefta	EG		30.71	31.24	111700
Zehlendorf	DE		52.43	13.25	54328
Zeist	NL		52.09	5.23	60949
Zelenodolsk	RU		55.84	48.52	99600
Zelenogorsk	RU		56.11	94.59	71354
Zelenograd	RU		55.98	37.18	215727
Zemun	RS		44.85	20.40	155591
Zenica	BA		44.20	17.90	164423
Zepu	CN		38.19	77.27	51691
Zerakpur	IN		30.66	76.82	95553
Zeytinburnu	TR		40.99	28.90	280896
Zgierz	PL		51.86	19.41	58036
Zhabei	CN		31.26	121.46	840000
Zhalantun	CN		48.01	122.74	132224
Zhanaozen	KZ		43.34	52.86	103598
Zhangfeng	CN		24.19	97.80	53370
Zhangji	CN		34.14	117.38	61929
Zhangjiachuan	CN		34.99	106.21	62497
Zhangjiagang	CN		31.86	120.54	1432044
Zhangjiajie	CN		29.13	110.48	441804
Zhangjiakou	CN		40.78	114.87	692602
Zhangye	CN		38.93	100.45	507433
Zhangzhai	CN		34.62	116.95	74433
Zhangzhou	CN		24.51	117.66	589831
Zhangzhuang	CN		34.52	117.01	74114
Zhanjiang	CN		21.23	110.39	1400709
Zhaobaoshan	CN		29.97	121.69	61979
Zhaodong	CN		46.05	125.96	154406
Zhaodun	CN		34.30	117.86	76691
Zhaogezhuang	CN		39.77	118.41	86555
Zhaoqing	CN		23.05	112.46	1553109
Zhaotong	CN		27.32	103.72	787845
Zhaoyuan	CN		37.36	120.41	120000
Zhaoyuan	CN		45.52	125.08	93505
Zhaozhou	CN		45.71	125.27	114009
Zhaozhuang	CN		34.74	116.46	53193
Zhawa	CN		37.21	79.63	52165
Zhefang	CN		24.27	98.28	51477
Zheleznodorozhnyy	RU		55.74	38.02	141648
Zheleznogorsk	RU		52.34	35.36	97900
Zheleznogorsk	RU		56.25	93.53	93834
Zhengding	CN		38.15	114.57	193524
Zhengzhou	CN		34.76	113.65	4253913
Zhenjiang	CN		32.21	119.46	950516
Zhenlai	CN		45.85	123.20	67760
Zhenping	CN		33.03	112.23	181528
Zhenxi	CN		29.90	107.46	50017
Zhenzhou	CN		32.28	119.17	176006
Zhezqazghan	KZ		47.79	67.71	104357
Zhicheng	CN		30.30	111.50	159383
Zhicheng	CN		31.01	119.91	63753
Zhigulëvsk	RU		53.40	49.51	57094
Zhijiang	CN		30.42	111.75	60169
Zhlobin	BY		52.89	30.02	76304
Zhob	PK		31.34	69.45	50537
Zhongduo	CN		28.85	108.76	93928
Zhonggulou	CN		30.82	108.38	85873
Zhonghe	CN		28.45	108.99	105003
Zhongshan	CN		22.52	113.38	3841873
Zhongshu	CN		24.52	103.77	91750
Zhongwei	CN		37.51	105.19	1174600
Zhongxiang	CN		31.17	112.58	108883
Zhongxin	CN		26.62	101.27	51866
Zhongxing	CN		33.70	118.68	57338
Zhoucheng	CN		35.91	116.31	72070
Zhoucun	CN		36.82	117.82	122402
Zhoujiaba	CN		30.84	108.37	88494
Zhoukou	CN		33.63	114.63	505171
Zhoushan	CN		29.99	122.20	882932
Zhu Cheng City	CN		36.00	119.40	1000000
Zhuanghe	CN		39.70	122.99	80384
Zhuangyuan	CN		37.31	120.83	79106
Zhubei	TW		24.84	121.01	212695
Zhucheng	CN		35.99	119.40	499285
Zhudong	TW		24.73	121.09	96518
Zhuhai	CN		22.28	113.57	2207090
Zhuji	CN		29.72	120.24	110721
Zhujiajiao	CN		31.11	121.06	60000
Zhujing	CN		30.90	121.16	120084
Zhukovsky	RU		55.60	38.12	97200
Zhulebino	RU		55.70	37.85	150000
Zhumadian	CN		32.98	114.03	721670
Zhutuo	CN		29.02	105.85	58262
Zhuyi	CN		31.03	109.39	55627
Zhuzhai	CN		34.76	116.81	56908
Zhuzhou	CN		27.83	113.15	1129687
Zhytomyr	UA		50.26	28.68	261624
Ziauddin Pur	IN		28.71	77.28	68993
Zibihu	CN		26.11	99.95	56246
Zibo	CN		36.79	118.06	3129228
Zielona Góra	PL		51.94	15.51	118433
Zigong	CN		29.34	104.78	1262064
Ziguinchor	SN		12.57	-16.27	214874
Zile	TR		40.30	35.89	55680
Zinacantepec	MX		19.28	-99.73	54220
Zinder	NE		13.81	8.99	318874
Zion	US	Illinois	42.45	-87.83	24117
Zionsville	US	Indiana	39.95	-86.26	26296
Zipaquirá	CO		5.02	-74.00	130432
Zitong	CN		30.18	105.83	212819
Ziway	ET		7.93	38.72	90500
Ziyang	CN		30.12	104.65	905729
Zizhuang	CN		34.36	117.49	52063
Zlatoust	RU		55.17	59.65	191366
Zliten	LY		32.47	14.57	203790
Zlín	CZ		49.23	17.67	72973
Zoetermeer	NL		52.06	4.49	115845
Zográfos	GR		37.98	23.77	71026
Zomba	MW		-15.39	35.32	118440
Zonguldak	TR		41.45	31.79	101749
Zoucheng	CN		35.40	116.97	277400
Zouérat	MR		22.74	-12.47	55183
Zrenjanin	RS		45.38	20.38	79773
Zugló	HU		47.52	19.11	130000
Zumpango	MX		19.80	-99.10	280455
Zunyi	CN		27.69	106.91	2037775
Zushi	JP		35.29	139.58	60055
Zvishavane	ZW		-20.33	30.07	59717
Zvyahel	UA		50.59	27.61	55925
Zwickau	DE		50.73	12.49	98796
Zwolle	NL		52.51	6.09	129840
Zyablikovo	RU		55.62	37.77	129000
Zyuzino	RU		55.66	37.57	121000
Zárate	AR		-34.10	-59.02	99061
Zürich	CH		47.37	8.55	415367
Zürich (Kreis 11)	CH		47.42	8.52	54260
Zābol	IR		31.03	61.49	121989
Água Rasa	BR		-20.43	-45.17	80484
Águas Claras	BR		-15.84	-48.03	128486
Águas Lindas de Goiás	BR		-15.76	-48.28	225693
Álvaro Obregón	MX		19.36	-99.20	726664
Ávila	ES		40.66	-4.70	57657
Ålesund	NO		62.47	6.15	52626
Århus	DK		56.16	10.21	285273
Çanakkale	TR		40.16	26.41	143622
Çankaya	TR		39.92	32.86	792189
Çankırı	TR		40.60	33.62	90564
Çarşamba	TR		41.20	36.72	50459
Çerkezköy	TR		41.29	28.00	84234
Çiğli	TR		38.50	27.07	214065
Çorlu	TR		41.16	27.80	202578
Çorum	TR		40.55	34.95	269595
Çubuk	TR		40.24	33.03	62602
Ébolowa	CM		2.90	11.15	101363
Érd	HU		47.39	18.91	62408
Évora	PT		38.57	-7.90	53591
Évosmos	GR		40.67	22.91	74686
Évreux	FR		49.02	1.15	57795
Évry	FR		48.63	2.44	51900
Ílion	GR		38.03	23.70	84793
Ðà Lạt	VN		11.95	108.44	258014
Ðông Hà	VN		16.82	107.10	164228
Ñuñoa	CL		-33.45	-70.58	255823
Óbidos	BR		-1.92	-55.52	52306
Ô Môn	VN		10.11	105.62	129683
Ödemiş	TR		38.23	27.97	67153
Örebro	SE		59.27	15.21	155989
Újpest	HU		47.57	19.08	100694
Ústí nad Labem	CZ		50.66	14.03	90378
Ünye	TR		41.14	37.29	77585
Ürümqi	CN		43.80	87.60	3029372
Üsküdar	TR		41.02	29.01	524452
Ābu Road	IN		24.48	72.78	55599
Ābyek	IR		36.04	50.53	60107
Ābyek	IR		36.07	50.55	55128
Ābādeh	IR		28.83	53.17	59116
Ādilābād	IN		19.67	78.54	118526
Ādīgrat	ET		14.28	39.46	121800
Āgaro	ET		7.85	36.65	52800
Ālbū Kamāl	SY		34.45	40.92	57572
Ālā'ĕr	CN		40.54	81.27	126259
Āmol	IR		36.47	52.35	237528
Āmūr	IN		18.79	78.28	64023
Ānaiyūr	IN		9.96	78.11	63917
Ānwén	CN		29.06	120.44	51994
Ārabī	ET		9.96	42.49	148933
Āreka	ET		7.07	37.70	84500
Ārān Bīdgol	IR		34.06	51.48	65404
Āsansol	IN		23.68	86.98	504271
Āsela	ET		7.95	39.13	139500
Āsosa	ET		10.07	34.53	69700
Čair	MK		42.02	21.44	64773
Čačak	RS		43.89	20.35	117072
České Budějovice	CZ		48.97	14.47	93426
Điện Bàn	VN		15.89	108.25	226564
Đưc Trọng	VN		11.74	108.37	161232
Đố Sơn	VN		20.71	106.79	51417
Đống Đa	VN		21.01	105.83	371606
Đồng Hới	VN		17.47	106.62	133672
Đồng Xoài	VN		11.53	106.88	168000
Đức Phổ	VN		14.81	108.96	155743
Īlām	IR		33.64	46.42	140940
Ītāy al Bārūd	EG		30.89	30.67	77606
Īz̄eh	IR		31.83	49.87	119399
Łomża	PL		53.18	22.06	62019
Łódź	PL		51.77	19.47	639890
Ōami	JP		35.52	140.32	53239
Ōbu	JP		35.02	136.95	93123
Ōdate	JP		40.27	140.56	69237
Ōgaki	JP		35.35	136.62	161539
Ōi	JP		35.85	139.52	50593
Ōita	JP		33.23	131.60	477715
Ōjima	JP		35.69	139.83	63254
Ōme	JP		35.78	139.24	133535
Ōmihachiman	JP		35.13	136.10	82233
Ōmura	JP		32.92	129.95	95397
Ōmuta	JP		33.03	130.45	131974
Ōnojō	JP		33.54	130.48	102085
Ōsaki	JP		38.59	140.97	128763
Ōshū	JP		39.14	141.17	112937
Ōta	JP		35.56	139.72	748081
Ōta	JP		36.30	139.37	224358
Ōtawara	JP		36.87	140.03	72087
Ōtsu	JP		35.00	135.87	345070
Ŏrang	KP		41.45	129.66	87757
Śródmieście	PL		52.23	21.02	99950
Śródmieście	PL		51.11	17.08	99088
Świdnica	PL		50.84	16.49	60351
Świętochłowice	PL		50.30	18.92	55600
Şabbāshahr	IR		35.58	51.11	53971
Şabrātah	LY		32.79	12.49	83398
Şabyā	SA		17.15	42.63	228375
Şabāḩ as Sālim	KW		29.26	48.06	139163
Şalālah	OM		17.02	54.09	163140
Şanlıurfa	TR		37.17	38.79	449549
Şaḩam	OM		24.17	56.89	140000
Şirvan	AZ		39.94	48.93	70220
Şişli	TR		41.06	28.99	314684
Şurmān	LY		32.76	12.57	77114
Şırnak	TR		37.51	42.45	67662
Šabac	RS		44.75	19.69	55114
Šiauliai	LT		55.93	23.32	99462
Ţahţā	EG		26.77	31.50	134314
Ţalkhā	EG		31.05	31.38	112851
Ţarīf Kalbā	AE		25.07	56.33	51000
Ţarţūs	SY		34.89	35.89	458327
Ţimā	EG		26.91	31.43	101130
Ţurayf	SA		31.67	38.66	66014
Ţāmiyah	EG		29.48	30.96	73070
Ţūkh	EG		30.35	31.20	52593
Ţūz Khūrmātū	IQ		34.89	44.63	120712
Ŭllyul	KP		38.51	125.19	107997
Ŭnch’ŏn-ŭp	KP		38.57	125.43	95597
Ŭndŏk	KP		42.52	130.33	89244
Żoliborz	PL		52.27	20.99	50934
Żory	PL		50.05	18.70	63174
Žilina	SK		49.22	18.74	81219
Žižkov	CZ		50.08	14.45	58267
ʻEwa Beach-Iroquois Point	US	Hawaii	21.32	-157.99	21088
ʻEwa Gentry-West Loch	US	Hawaii	21.35	-158.03	35828
Ḩadā’iq al Qubbah	EG		30.09	31.28	339612
Ḩalwān	EG		29.84	31.30	230000
Ḩamāh	SY		35.13	36.76	460602
Ḩawallī	KW		29.33	48.03	164212
Ḩawsh ‘Īsá	EG		30.91	30.29	82999
Ḩayy Khildā	JO		31.99	35.84	251000
Ṣuwayliḥ	JO		32.02	35.84	151016
Ṣāleḥīeh	IR		35.51	51.19	58683
‘Ajlūn	JO		32.33	35.75	125557
‘Alemaya	ET		9.39	42.01	63700
‘Amrān	YE		15.66	43.94	90792
‘Ayn al ‘Arab	SY		36.89	38.35	50000
‘Ewa Beach	US	Hawaii	21.32	-158.01	16415
‘Ewa Gentry	US	Hawaii	21.34	-158.03	22690
‘Ibrī	OM		23.23	56.52	163473
‘Izbat ‘Alī as Sayyid	EG		31.16	30.15	53079
"""

# Country codes and names (GeoNames).
COUNTRIES = """\
AD	Andorra
AE	United Arab Emirates
AF	Afghanistan
AG	Antigua and Barbuda
AI	Anguilla
AL	Albania
AM	Armenia
AN	Netherlands Antilles
AO	Angola
AQ	Antarctica
AR	Argentina
AS	American Samoa
AT	Austria
AU	Australia
AW	Aruba
AX	Aland Islands
AZ	Azerbaijan
BA	Bosnia and Herzegovina
BB	Barbados
BD	Bangladesh
BE	Belgium
BF	Burkina Faso
BG	Bulgaria
BH	Bahrain
BI	Burundi
BJ	Benin
BL	Saint Barthelemy
BM	Bermuda
BN	Brunei
BO	Bolivia
BQ	Bonaire, Saint Eustatius and Saba 
BR	Brazil
BS	Bahamas
BT	Bhutan
BV	Bouvet Island
BW	Botswana
BY	Belarus
BZ	Belize
CA	Canada
CC	Cocos Islands
CD	Democratic Republic of the Congo
CF	Central African Republic
CG	Republic of the Congo
CH	Switzerland
CI	Ivory Coast
CK	Cook Islands
CL	Chile
CM	Cameroon
CN	China
CO	Colombia
CR	Costa Rica
CS	Serbia and Montenegro
CU	Cuba
CV	Cabo Verde
CW	Curacao
CX	Christmas Island
CY	Cyprus
CZ	Czechia
DE	Germany
DJ	Djibouti
DK	Denmark
DM	Dominica
DO	Dominican Republic
DZ	Algeria
EC	Ecuador
EE	Estonia
EG	Egypt
EH	Western Sahara
ER	Eritrea
ES	Spain
ET	Ethiopia
FI	Finland
FJ	Fiji
FK	Falkland Islands
FM	Micronesia
FO	Faroe Islands
FR	France
GA	Gabon
GB	United Kingdom
GD	Grenada
GE	Georgia
GF	French Guiana
GG	Guernsey
GH	Ghana
GI	Gibraltar
GL	Greenland
GM	Gambia
GN	Guinea
GP	Guadeloupe
GQ	Equatorial Guinea
GR	Greece
GS	South Georgia and the South Sandwich Islands
GT	Guatemala
GU	Guam
GW	Guinea-Bissau
GY	Guyana
HK	Hong Kong
HM	Heard Island and McDonald Islands
HN	Honduras
HR	Croatia
HT	Haiti
HU	Hungary
ID	Indonesia
IE	Ireland
IL	Israel
IM	Isle of Man
IN	India
IO	British Indian Ocean Territory
IQ	Iraq
IR	Iran
IS	Iceland
IT	Italy
JE	Jersey
JM	Jamaica
JO	Jordan
JP	Japan
KE	Kenya
KG	Kyrgyzstan
KH	Cambodia
KI	Kiribati
KM	Comoros
KN	Saint Kitts and Nevis
KP	North Korea
KR	South Korea
KW	Kuwait
KY	Cayman Islands
KZ	Kazakhstan
LA	Laos
LB	Lebanon
LC	Saint Lucia
LI	Liechtenstein
LK	Sri Lanka
LR	Liberia
LS	Lesotho
LT	Lithuania
LU	Luxembourg
LV	Latvia
LY	Libya
MA	Morocco
MC	Monaco
MD	Moldova
ME	Montenegro
MF	Saint Martin
MG	Madagascar
MH	Marshall Islands
MK	North Macedonia
ML	Mali
MM	Myanmar
MN	Mongolia
MO	Macao
MP	Northern Mariana Islands
MQ	Martinique
MR	Mauritania
MS	Montserrat
MT	Malta
MU	Mauritius
MV	Maldives
MW	Malawi
MX	Mexico
MY	Malaysia
MZ	Mozambique
NA	Namibia
NC	New Caledonia
NE	Niger
NF	Norfolk Island
NG	Nigeria
NI	Nicaragua
NL	The Netherlands
NO	Norway
NP	Nepal
NR	Nauru
NU	Niue
NZ	New Zealand
OM	Oman
PA	Panama
PE	Peru
PF	French Polynesia
PG	Papua New Guinea
PH	Philippines
PK	Pakistan
PL	Poland
PM	Saint Pierre and Miquelon
PN	Pitcairn
PR	Puerto Rico
PS	Palestinian Territory
PT	Portugal
PW	Palau
PY	Paraguay
QA	Qatar
RE	Reunion
RO	Romania
RS	Serbia
RU	Russia
RW	Rwanda
SA	Saudi Arabia
SB	Solomon Islands
SC	Seychelles
SD	Sudan
SE	Sweden
SG	Singapore
SH	Saint Helena
SI	Slovenia
SJ	Svalbard and Jan Mayen
SK	Slovakia
SL	Sierra Leone
SM	San Marino
SN	Senegal
SO	Somalia
SR	Suriname
SS	South Sudan
ST	Sao Tome and Principe
SV	El Salvador
SX	Sint Maarten
SY	Syria
SZ	Eswatini
TC	Turks and Caicos Islands
TD	Chad
TF	French Southern Territories
TG	Togo
TH	Thailand
TJ	Tajikistan
TK	Tokelau
TL	Timor Leste
TM	Turkmenistan
TN	Tunisia
TO	Tonga
TR	Turkey
TT	Trinidad and Tobago
TV	Tuvalu
TW	Taiwan
TZ	Tanzania
UA	Ukraine
UG	Uganda
UM	United States Minor Outlying Islands
US	United States
UY	Uruguay
UZ	Uzbekistan
VA	Vatican
VC	Saint Vincent and the Grenadines
VE	Venezuela
VG	British Virgin Islands
VI	U.S. Virgin Islands
VN	Vietnam
VU	Vanuatu
WF	Wallis and Futuna
WS	Samoa
XK	Kosovo
YE	Yemen
YT	Mayotte
ZA	South Africa
ZM	Zambia
ZW	Zimbabwe
"""

# US states: postal code and name (GeoNames).
US_STATES = """\
AK	Alaska
AL	Alabama
AR	Arkansas
AZ	Arizona
CA	California
CO	Colorado
CT	Connecticut
DC	District of Columbia
DE	Delaware
FL	Florida
GA	Georgia
HI	Hawaii
IA	Iowa
ID	Idaho
IL	Illinois
IN	Indiana
KS	Kansas
KY	Kentucky
LA	Louisiana
MA	Massachusetts
MD	Maryland
ME	Maine
MI	Michigan
MN	Minnesota
MO	Missouri
MS	Mississippi
MT	Montana
NC	North Carolina
ND	North Dakota
NE	Nebraska
NH	New Hampshire
NJ	New Jersey
NM	New Mexico
NV	Nevada
NY	New York
OH	Ohio
OK	Oklahoma
OR	Oregon
PA	Pennsylvania
RI	Rhode Island
SC	South Carolina
SD	South Dakota
TN	Tennessee
TX	Texas
UT	Utah
VA	Virginia
VT	Vermont
WA	Washington
WI	Wisconsin
WV	West Virginia
WY	Wyoming
"""
