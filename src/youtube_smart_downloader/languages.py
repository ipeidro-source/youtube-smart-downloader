"""ISO 639-1 to ISO 639-2/T tags used by multimedia containers.

Regional/script information is retained separately in the track title.
"""

_ISO_639_2 = dict(
    pair.split(":")
    for pair in """
aa:aar ab:abk ae:ave af:afr ak:aka am:amh an:arg ar:ara as:asm av:ava ay:aym az:aze
ba:bak be:bel bg:bul bh:bih bi:bis bm:bam bn:ben bo:bod br:bre bs:bos
ca:cat ce:che ch:cha co:cos cr:cre cs:ces cu:chu cv:chv cy:cym
da:dan de:deu dv:div dz:dzo ee:ewe el:ell en:eng eo:epo es:spa et:est eu:eus
fa:fas ff:ful fi:fin fj:fij fo:fao fr:fra fy:fry
ga:gle gd:gla gl:glg gn:grn gu:guj gv:glv
ha:hau he:heb hi:hin ho:hmo hr:hrv ht:hat hu:hun hy:hye hz:her
ia:ina id:ind ie:ile ig:ibo ii:iii ik:ipk io:ido is:isl it:ita iu:iku
ja:jpn jv:jav ka:kat kg:kon ki:kik kj:kua kk:kaz kl:kal km:khm kn:kan
ko:kor kr:kau ks:kas ku:kur kv:kom kw:cor ky:kir
la:lat lb:ltz lg:lug li:lim ln:lin lo:lao lt:lit lu:lub lv:lav
mg:mlg mh:mah mi:mri mk:mkd ml:mal mn:mon mr:mar ms:msa mt:mlt my:mya
na:nau nb:nob nd:nde ne:nep ng:ndo nl:nld nn:nno no:nor nr:nbl nv:nav ny:nya
oc:oci oj:oji om:orm or:ori os:oss pa:pan pi:pli pl:pol ps:pus pt:por
qu:que rm:roh rn:run ro:ron ru:rus rw:kin
sa:san sc:srd sd:snd se:sme sg:sag si:sin sk:slk sl:slv sm:smo sn:sna
so:som sq:sqi sr:srp ss:ssw st:sot su:sun sv:swe sw:swa
ta:tam te:tel tg:tgk th:tha ti:tir tk:tuk tl:tgl tn:tsn to:ton tr:tur ts:tso tt:tat tw:twi ty:tah
ug:uig uk:ukr ur:urd uz:uzb ve:ven vi:vie vo:vol wa:wln wo:wol
xh:xho yi:yid yo:yor za:zha zh:zho zu:zul
""".split()
)


def container_language(language: str) -> str:
    base = language.lower().replace("_", "-").split("-")[0]
    return _ISO_639_2.get(base, base if len(base) == 3 and base.isalpha() else "und")


# Human-readable language picker; codes are shown alongside names in the UI.
LANGUAGE_NAMES = dict(
    line.split("|", 1)
    for line in """
aa|Afar
ab|Abkhazian
ae|Avestan
af|Afrikaans
ak|Akan
am|Amharic
an|Aragonese
ar|Arabic
as|Assamese
av|Avaric
ay|Aymara
az|Azerbaijani
ba|Bashkir
be|Belarusian
bg|Bulgarian
bh|Bihari
bi|Bislama
bm|Bambara
bn|Bengali
bo|Tibetan
br|Breton
bs|Bosnian
ca|Catalan
ce|Chechen
ch|Chamorro
co|Corsican
cr|Cree
cs|Czech
cu|Church Slavic
cv|Chuvash
cy|Welsh
da|Danish
de|German
dv|Divehi
dz|Dzongkha
ee|Ewe
el|Greek
en|English (any region)
eo|Esperanto
es|Spanish (any region)
et|Estonian
eu|Basque
fa|Persian
ff|Fulah
fi|Finnish
fj|Fijian
fo|Faroese
fr|French
fy|Western Frisian
ga|Irish
gd|Gaelic
gl|Galician
gn|Guarani
gu|Gujarati
gv|Manx
ha|Hausa
he|Hebrew
hi|Hindi
ho|Hiri Motu
hr|Croatian
ht|Haitian Creole
hu|Hungarian
hy|Armenian
hz|Herero
ia|Interlingua
id|Indonesian
ie|Interlingue
ig|Igbo
ii|Sichuan Yi
ik|Inupiaq
io|Ido
is|Icelandic
it|Italian
iu|Inuktitut
ja|Japanese
jv|Javanese
ka|Georgian
kg|Kongo
ki|Kikuyu
kj|Kuanyama
kk|Kazakh
kl|Kalaallisut
km|Khmer
kn|Kannada
ko|Korean
kr|Kanuri
ks|Kashmiri
ku|Kurdish
kv|Komi
kw|Cornish
ky|Kirghiz
la|Latin
lb|Luxembourgish
lg|Ganda
li|Limburgan
ln|Lingala
lo|Lao
lt|Lithuanian
lu|Luba-Katanga
lv|Latvian
mg|Malagasy
mh|Marshallese
mi|Maori
mk|Macedonian
ml|Malayalam
mn|Mongolian
mr|Marathi
ms|Malay
mt|Maltese
my|Burmese
na|Nauru
nb|Norwegian Bokmal
nd|North Ndebele
ne|Nepali
ng|Ndonga
nl|Dutch
nn|Norwegian Nynorsk
no|Norwegian
nr|South Ndebele
nv|Navajo
ny|Chichewa
oc|Occitan
oj|Ojibwa
om|Oromo
or|Oriya
os|Ossetian
pa|Panjabi
pi|Pali
pl|Polish
ps|Pushto
pt|Portuguese (any region)
qu|Quechua
rm|Romansh
rn|Rundi
ro|Romanian
ru|Russian
rw|Kinyarwanda
sa|Sanskrit
sc|Sardinian
sd|Sindhi
se|Northern Sami
sg|Sango
si|Sinhala
sk|Slovak
sl|Slovenian
sm|Samoan
sn|Shona
so|Somali
sq|Albanian
sr|Serbian
ss|Swati
st|Southern Sotho
su|Sundanese
sv|Swedish
sw|Swahili
ta|Tamil
te|Telugu
tg|Tajik
th|Thai
ti|Tigrinya
tk|Turkmen
tl|Tagalog
tn|Tswana
to|Tonga
tr|Turkish
ts|Tsonga
tt|Tatar
tw|Twi
ty|Tahitian
ug|Uighur
uk|Ukrainian
ur|Urdu
uz|Uzbek
ve|Venda
vi|Vietnamese
vo|Volapuk
wa|Walloon
wo|Wolof
xh|Xhosa
yi|Yiddish
yo|Yoruba
za|Zhuang
zh|Chinese (any region)
zu|Zulu
es-ES|Spanish (Spain)
es-419|Spanish (Latin America)
en-US|English (United States)
en-GB|English (United Kingdom)
pt-BR|Portuguese (Brazil)
pt-PT|Portuguese (Portugal)
zh-Hans|Chinese (Simplified)
zh-Hant|Chinese (Traditional)
""".strip().splitlines()
)
