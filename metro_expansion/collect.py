import concurrent.futures,hashlib,json,re,subprocess,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parent;RAW=ROOT/'raw';RAW.mkdir(exist_ok=True)
jobs=[]
for dataset in ['OA-22197','OA-12035','OA-12034']:
    url=f'https://data.seoul.go.kr/dataList/{dataset}/F/1/datasetView.do'
    html=urllib.request.urlopen(url).read().decode('utf-8');(RAW/f'{dataset}.html').write_text(html)
    rows=re.findall(r'<span title="([^"]+)" onclick="javascript:downloadFile\(\'(\d+)\'\);">',html)
    print(dataset,rows[:3],flush=True)
    form=re.search(r'<form name="frmFile".*?</form>',html,re.S)[0]
    infseq=re.search(r'name="infSeq" value="([^"]+)"',form)[1]
    for name,seq in (rows[:3] if dataset=='OA-22197' else rows[:1]):jobs.append(dict(dataset=dataset,filename=name,seq=seq,infSeq=infseq,page=url))
def fetch(job):
    p=RAW/job['filename'];url='https://datafile.seoul.go.kr/bigfile/iot/inf/nio_download.do?useCache=false'
    if not p.exists() or p.read_bytes().lstrip().startswith(b'<html'):subprocess.run(['curl','-fsSL','--retry','2','--max-time','90','-d',f"infId={job['dataset']}&seq={job['seq']}&infSeq={job['infSeq']}",url,'-o',str(p)],check=True)
    assert not p.read_bytes().lstrip().startswith(b'<html'),p
    job.update(url=url,bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest());print('saved',job['filename'],job['bytes'],flush=True);return job
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool: result=list(pool.map(fetch,jobs))
(ROOT/'manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
