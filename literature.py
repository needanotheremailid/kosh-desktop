"""Explicit public catalogue queries. No document upload or full-text download."""
from __future__ import annotations
import copy
import html
import json
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote, unquote
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
import xml.etree.ElementTree as ET

PROVIDERS = {"pubmed": "PubMed", "crossref": "Crossref", "europepmc": "Europe PMC", "openalex": "OpenAlex"}
LIMIT = 20
MAX_RESPONSE = 2 * 1024 * 1024

class LiteratureError(Exception):
    pass

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise LiteratureError("The index redirected its API request. No redirected request was sent.")

def clean(value, maximum=1200):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r'</?[A-Za-z][^>]*>', '', str(value or '')))).strip()[:maximum]

def doi_value(value):
    value = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", clean(value, 300), flags=re.I)
    value = unquote(value)
    return value if re.fullmatch(r"10\.\d{4,9}/[^\s<>\x00]+", value) else ""

def record(provider, id_, title, **fields):
    result = {key: "" for key in ("authors", "year", "doi", "journal", "journal_abbreviation", "volume", "issue", "pages", "url", "abstract")}
    result.update(provider=provider, id=clean(id_, 200), title=clean(title,1000), author_list=[], type="other", warnings=list(fields.get('warnings',[])))
    if len(clean(title,100000))>1000: result['warnings'].append('Title shortened to the bounded metadata field; verify complete title.')
    for key in result.keys() & fields.keys():
        if key == "author_list":
            result[key] = [({'literal': clean(a['literal'], 200)} if a.get('literal') else {"family":clean(a.get("family"),200),"given":clean(a.get("given"),200)}) for a in fields[key][:200] if clean(a.get('family') or a.get('literal'))]
            if len(fields[key])>200: result['warnings'].append('Author list truncated at 200 names; reference is incomplete.')
            if any(len(str(a.get(part,'')))>200 for a in fields[key] for part in ('family','given','literal')): result['warnings'].append('An author name was shortened to the bounded field; verify names.')
        elif key=='warnings':
            continue
        else:
            maximum=4000 if key in {'authors','abstract'} else 1000
            result[key] = clean(fields[key],maximum)
            if len(clean(fields[key],1000000))>maximum: result['warnings'].append(key.replace('_',' ').title()+' truncated to the bounded metadata field; reference needs review.')
    result["doi"] = doi_value(result["doi"])
    return result

def json_fetch(url):
    return json.loads(fetch(url).decode("utf-8"))

def fetch(url):
    request = Request(url, headers={"User-Agent":"Kosh/0.1 (explicit catalogue search)","Accept":"application/json, application/xml;q=0.9"})
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=15) as response:
            data = response.read(MAX_RESPONSE + 1)
        if len(data) > MAX_RESPONSE:
            raise LiteratureError("The index response exceeds the bounded metadata limit.")
        return data
    except HTTPError as error:
        if error.code == 429:
            raise LiteratureError("The index rate limit was reached. Wait before searching again; no automatic retry was sent.") from None
        raise LiteratureError(f"The index returned HTTP {error.code}. No library records were changed.") from None
    except (URLError, TimeoutError, OSError):
        raise LiteratureError("The index is unavailable or timed out. Your saved library is unchanged.") from None

def _author_text(authors):
    return '; '.join(a['literal'] if a.get('literal') else (a['family'] + (', ' + a['given'] if a.get('given') else '')) for a in authors)

def _crossref_record(value):
    doi=doi_value(value.get("DOI"))
    if not doi:
        return None
    authors=[]
    for author in value.get('author',[]):
        if author.get('family'):
            authors.append({'family':author['family'],'given':author.get('given','')})
        elif author.get('name'):
            authors.append({'literal':author['name']})
    year=""
    for field in ("published-print","published-online","published","issued"):
        parts=value.get(field,{}).get("date-parts",[])
        if parts and parts[0]:
            year=str(parts[0][0]);break
    return record("crossref",doi,(value.get("title") or [""])[0],doi=doi,authors=_author_text(authors),author_list=authors,year=year,journal=(value.get("container-title") or [""])[0],journal_abbreviation=(value.get("short-container-title") or [""])[0],volume=value.get("volume"),issue=value.get("issue"),pages=value.get("page"),abstract=value.get('abstract',''),type="journal_article" if value.get("type")=="journal-article" else "other",url="https://doi.org/"+quote(doi,safe="/"))

def crossref(query):
    data = json_fetch("https://api.crossref.org/works?"+urlencode({"query.bibliographic":query,"rows":LIMIT}))
    message = data.get("message", {})
    items=[item for value in message.get("items", [])[:LIMIT] if (item:=_crossref_record(value)) is not None]
    return message.get("total-results",len(items)),items

def pubmed(query):
    base="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    data=json_fetch(base+"esearch.fcgi?"+urlencode({"db":"pubmed","term":query,"retmode":"json","retmax":LIMIT,"tool":"Kosh"}))
    result=data.get("esearchresult",{})
    ids=[str(x) for x in result.get("idlist",[])[:LIMIT] if re.fullmatch(r"\d{1,12}",str(x))]
    if not ids:
        return int(result.get("count",0)),[]
    time.sleep(0.36)  # Two NCBI requests stay below the keyless per-second limit.
    xml=fetch(base+"efetch.fcgi?"+urlencode({"db":"pubmed","id":",".join(ids),"retmode":"xml","tool":"Kosh"}))
    return int(result.get("count",len(ids))),_pubmed_records(xml)

def _pubmed_records(xml):
    if b"<!ENTITY" in xml.upper():
        raise LiteratureError("The index returned unsupported XML entities.")
    root=ET.fromstring(xml)
    items=[]
    text=lambda element,path: "".join(element.find(path).itertext()) if element.find(path) is not None else ""
    for value in root.findall("PubmedArticle")[:LIMIT]:
        article=value.find("MedlineCitation/Article")
        if article is None:continue
        pmid=text(value,"MedlineCitation/PMID")
        if not re.fullmatch(r"\d{1,12}",pmid):continue
        authors=[]
        for author in article.findall("AuthorList/Author"):
            if text(author,"CollectiveName"):
                authors.append({'literal':text(author,"CollectiveName")})
            elif text(author,"LastName"):
                authors.append({'family':text(author,"LastName"),'given':text(author,"ForeName") or ' '.join(text(author,"Initials"))})
        abstract=' '.join((section.get('Label','')+': ' if section.get('Label') else '')+''.join(section.itertext()) for section in article.findall('Abstract/AbstractText'))
        doi=next((x.text or "" for x in value.findall("PubmedData/ArticleIdList/ArticleId") if x.get("IdType")=="doi"),"")
        year=text(article,"Journal/JournalIssue/PubDate/Year")
        # MedlineDate is retained literally; no unreported publication year is guessed.
        if not year: year=text(article,"Journal/JournalIssue/PubDate/MedlineDate")
        items.append(record("pubmed",pmid,text(article,"ArticleTitle"),authors=_author_text(authors),author_list=authors,year=year,doi=doi,journal=text(article,"Journal/Title"),journal_abbreviation=text(value,"MedlineCitation/MedlineJournalInfo/MedlineTA"),volume=text(article,"Journal/JournalIssue/Volume"),issue=text(article,"Journal/JournalIssue/Issue"),pages=text(article,"Pagination/MedlinePgn"),abstract=abstract,type="journal_article",url="https://pubmed.ncbi.nlm.nih.gov/"+pmid+"/"))
        items[-1]['pmid']=pmid  # record() keeps a fixed key set; saved references and completion need the PMID.
    return items

def europepmc(query):
    data=json_fetch("https://www.ebi.ac.uk/europepmc/webservices/rest/search?"+urlencode({"query":query,"format":"json","pageSize":LIMIT,"resultType":"core"}))
    items=[]
    for value in data.get("resultList",{}).get("result",[])[:LIMIT]:
        id_=clean(value.get("id"),100);source=clean(value.get("source"),20)
        if not re.fullmatch(r"[A-Z0-9]+",source) or not re.fullmatch(r"[A-Za-z0-9_.-]+",id_):continue
        authors=[]
        for author in (value.get('authorList') or {}).get('author',[]):
            if author.get('collectiveName'):
                authors.append({'literal':author['collectiveName']})
            elif author.get('lastName'):
                authors.append({'family':author['lastName'],'given':author.get('firstName','')})
            elif author.get('fullName'):
                authors.append({'literal':author['fullName']})
        journal_info=value.get('journalInfo') or {};journal=journal_info.get('journal') or {}
        items.append(record("europepmc",source+":"+id_,value.get("title"),authors=_author_text(authors) if authors else value.get("authorString"),author_list=authors,year=value.get("pubYear"),doi=value.get("doi"),journal=value.get("journalTitle") or journal.get('title'),journal_abbreviation=journal.get('medlineAbbreviation') or journal.get('ISOAbbreviation'),volume=value.get("journalVolume") or journal_info.get('volume'),issue=value.get("issue") or journal_info.get('issue'),pages=value.get("pageInfo"),abstract=value.get('abstractText',''),type="journal_article" if source=="MED" else "other",url="https://europepmc.org/article/"+source+"/"+id_))
    return data.get("hitCount",len(items)),items

def openalex(query):
    data=json_fetch("https://api.openalex.org/works?"+urlencode({"search":query,"per-page":LIMIT}))
    items=[]
    for value in data.get("results",[])[:LIMIT]:
        id_=clean(value.get("id")).rsplit("/",1)[-1]
        if not re.fullmatch(r"W\d+",id_):continue
        biblio=value.get("biblio") or {};location=value.get("primary_location") or {};source=location.get("source") or {}
        pages="-".join(str(biblio[x]) for x in ("first_page","last_page") if biblio.get(x))
        names=value.get('authorships',[])
        warnings=['Author list truncated at 200 names; reference is incomplete.'] if len(names)>200 else []
        if any(len(str(a.get('author',{}).get('display_name','')))>200 for a in names): warnings.append('An author name was shortened; verify complete names.')
        authors=[{'literal':a.get('author',{}).get('display_name','')} for a in names if a.get('author',{}).get('display_name')]
        inverted=value.get('abstract_inverted_index')
        words={}
        if inverted is not None:
            if not isinstance(inverted,dict):raise LiteratureError('The index returned an unsupported abstract index.')
            for word,positions in inverted.items():
                if not isinstance(word,str) or not isinstance(positions,list):raise LiteratureError('The index returned an unsupported abstract index.')
                for position in positions:
                    if type(position) is not int or not 0<=position<16000 or position in words:raise LiteratureError('The index returned an inconsistent abstract index.')
                    words[position]=word
        abstract=' '.join(words[position] for position in sorted(words))
        if words and sorted(words)!=list(range(max(words)+1)):
            abstract='';warnings.append('Abstract index has missing positions; incomplete abstract was omitted.')
        items.append(record("openalex",id_,value.get("title"),authors=_author_text(authors),author_list=authors,warnings=warnings,year=value.get("publication_year"),doi=value.get("doi"),journal=source.get("display_name"),volume=biblio.get("volume"),issue=biblio.get("issue"),pages=pages,abstract=abstract,type="journal_article" if value.get("type")=="article" and source.get("type")=="journal" else "other",url="https://openalex.org/"+id_))
    return data.get("meta",{}).get("count",len(items)),items

class SearchService:
    def __init__(self):
        self.lock=threading.Lock();self.cache={};self.last={}

    def _start_request(self,provider):
        with self.lock:
            current=time.monotonic()
            if current-self.last.get(provider,0)<1.0:raise LiteratureError("Wait a moment before querying this index again.")
            self.last[provider]=current

    def _remember(self,items):
        retrieved=datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self.lock:
            self.cache={key:value for key,value in self.cache.items() if time.monotonic()-value[0]<1800}
            for item in items:
                item['result_id']=uuid.uuid4().hex;item['retrieved_at']=retrieved
                self.cache[item['result_id']]=(time.monotonic(),copy.deepcopy(item))
            while len(self.cache)>200:self.cache.pop(next(iter(self.cache)))
        return retrieved

    def lookup(self,provider,identifier,identifier_type='doi'):
        """Exact approved metadata lookup; no fuzzy search, fallback or paper download.

        Parent route: POST /api/literature/lookup with provider, identifier,
        identifier_type and workspace_id (workspace validation belongs to parent).
        Crossref supports DOI; PubMed supports PMID. Result IDs use the same
        bounded cache and explicit /literature/save flow as catalogue queries.
        """
        if (provider,identifier_type) not in {('crossref','doi'),('pubmed','pmid')}:
            raise LiteratureError('Exact DOI lookup uses Crossref; exact PMID lookup uses PubMed.')
        if not isinstance(identifier,str) or not identifier.strip() or len(identifier)>500 or any(ord(ch)<32 for ch in identifier):
            raise LiteratureError('Enter one DOI or PMID without control characters.')
        identifier=identifier.strip()
        if identifier_type=='doi':
            identifier=doi_value(identifier)
            if not identifier:raise LiteratureError('Enter a valid DOI, doi: identifier or doi.org URL.')
        elif not re.fullmatch(r'[1-9]\d{0,11}',identifier):
            raise LiteratureError('Enter a PMID containing 1–12 digits without query syntax.')
        self._start_request(provider)
        try:
            if provider=='crossref':
                value=json_fetch('https://api.crossref.org/works/'+quote(identifier,safe='')).get('message',{})
                item=_crossref_record(value)
                if item is None or item['doi'].casefold()!=identifier.casefold():
                    raise LiteratureError('The index did not return the requested DOI. No reference was saved.')
                items=[item]
            else:
                xml=fetch('https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?'+urlencode({'db':'pubmed','id':identifier,'retmode':'xml','tool':'Kosh'}))
                items=_pubmed_records(xml)
                if len(items)!=1 or items[0]['id']!=identifier:
                    raise LiteratureError('The index did not return the requested PMID. No reference was saved.')
        except LiteratureError:raise
        except (ValueError,TypeError,KeyError,ET.ParseError,AttributeError):
            raise LiteratureError('The index returned an unsupported metadata response. Nothing was saved.') from None
        retrieved=self._remember(items)
        return {'provider':provider,'query':identifier,'identifier':identifier,'identifier_type':identifier_type,'retrieved_at':retrieved,'total':len(items),'results':items,'notice':'Exact identifier catalogue metadata only. Abstract is included only when the index supplies it; absence is not inferred from another source. No full paper was downloaded or analysed.'}

    def search(self,provider,query):
        if provider == 'all':
            combined, identities, errors, totals = [], {}, [], {}
            for index in PROVIDERS:
                try:
                    batch = self.search(index, query)
                    totals[index] = batch['total']
                    for item in batch['results']:
                        identity = ('doi:' + doi_value(item['doi']).casefold()) if item.get('doi') else index + ':' + item['id']
                        if identity in identities:
                            identities[identity]['providers'].append(index)
                        else:
                            item['providers'] = [index]
                            identities[identity] = item
                            combined.append(item)
                except LiteratureError as error:
                    errors.append({'provider': index, 'error': str(error)})
            if not combined and len(errors) == len(PROVIDERS):
                raise LiteratureError('All selected indexes failed: ' + '; '.join(item['provider'] + ': ' + item['error'] for item in errors))
            with self.lock:
                for item in combined:
                    self.cache[item['result_id']] = (time.monotonic(), copy.deepcopy(item))
                while len(self.cache)>200:self.cache.pop(next(iter(self.cache)))
            return {'provider': 'all', 'query': query, 'results': combined, 'total': len(combined), 'provider_totals': totals, 'errors': errors, 'retrieved_at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'notice': 'First bounded page from each index, deduplicated by DOI. This is not an exhaustive literature search. Failed indexes are listed; no papers were downloaded.'}
        if provider not in PROVIDERS:raise LiteratureError("Choose an available public index.")
        if not isinstance(query,str) or not query.strip() or len(query)>500 or any(ord(c)<32 for c in query):
            raise LiteratureError("Enter a public search query of 1–500 characters without control characters.")
        self._start_request(provider)
        try:
            total,items=globals()[provider](query.strip())
        except LiteratureError:raise
        except (ValueError,TypeError,KeyError,ET.ParseError,AttributeError):
            raise LiteratureError("The index returned an unsupported metadata response. Nothing was saved.") from None
        retrieved=self._remember(items)
        return {"provider":provider,"query":query.strip(),"retrieved_at":retrieved,"total":int(total),"results":items,"notice":"Public catalogue metadata only. No full paper was downloaded or analysed. Verify metadata against the publication before submission."}

    def get_result(self,result_id):
        with self.lock:
            value=self.cache.get(result_id) if isinstance(result_id,str) else None
            if value is None or time.monotonic()-value[0]>1800:
                raise LiteratureError("This result expired. Search again before saving it.")
            return copy.deepcopy(value[1])

def bibtex(item):
    """Make an inert catalogue record. Imported bytes never become commands."""
    def escaped(value,raw=False):
        symbols={"\\":r"\textbackslash{}","{":r"\{","}":r"\}",'\r':' ','\n':' '}
        if not raw:symbols.update({'&':r'\&','%':r'\%','#':r'\#','_':r'\_','$':r'\$','~':r'\textasciitilde{}','^':r'\textasciicircum{}'})
        return ''.join(symbols.get(ch,ch) for ch in str(value))
    fields={key:item.get(key,"") for key in ("title","year","doi","journal","volume","pages","abstract")}
    if item.get("issue"):fields["number"]=item["issue"]
    authors=[]
    for author in item.get('author_list',[]):
        if author.get('literal'):
            authors.append('{'+escaped(author['literal'])+'}')
        else:
            authors.append(escaped(author['family'])+(', '+escaped(author['given']) if author.get('given') else ''))
    if not authors and item.get('authors'):authors=['{'+escaped(item['authors'])+'}']
    if authors:fields['author']=' and '.join(authors)
    fields["url"]=item["url"]
    fields["note"]="Catalogue metadata from "+PROVIDERS[item["provider"]]+"; not the full article; verify against publication. "+' '.join(item.get('warnings',[]))
    kind="article" if item.get("type")=="journal_article" else "misc"
    key="Kosh"+re.sub(r"[^A-Za-z0-9]","",item["id"])[-80:]
    return ("@"+kind+"{"+key+",\n"+",\n".join("  "+name+" = {"+(value if name=='author' else escaped(value,raw=name in {'doi','url'}))+"}" for name,value in fields.items() if value)+"\n}\n").encode("utf-8")
