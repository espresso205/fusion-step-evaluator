"""Standard-library stdio MCP boundary around the unchanged STEP evaluator.

One JSON-RPC message per UTF-8 line. Only protocol responses go to stdout.
Configuration is administrator-owned; callers cannot choose commands or outputs.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time
import uuid

BASE = Path(__file__).resolve().parent
PROTOCOL = 'fusion-step-adapted-v4.0'
SUPPORTED_PROTOCOLS = ('fusion-step-adapted-v3.0', PROTOCOL)
MCP_VERSIONS = ('2025-06-18', '2025-03-26', '2024-11-05')
MAX_MESSAGE = 1024 * 1024


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'),
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('non-finite JSON value')))


def write_json(path, data):
    path = Path(path)
    temp = path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+'\n',encoding='utf-8')
    temp.replace(path)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def object_schema(properties, required=()):
    return {'type':'object','properties':properties,'required':list(required),'additionalProperties':False}


STRING = {'type':'string','minLength':1}
PROTOCOL_SCHEMA = {'type':'string','enum':list(SUPPORTED_PROTOCOLS)}
COORDINATE_SCHEMA = {'type':'string','enum':['geometry','strict']}


def scoring_options(config):
    protocol = config.get('protocol', PROTOCOL)
    if protocol not in SUPPORTED_PROTOCOLS:
        raise ValueError('unsupported scoring protocol')
    mode = config.get('coordinate_mode', 'geometry' if protocol==PROTOCOL else 'strict')
    if mode not in ('geometry','strict') or protocol!=PROTOCOL and mode!='strict':
        raise ValueError('coordinate_mode must be geometry/strict; v3 requires strict')
    return protocol, mode


TOOLS = [
    {'name':'evaluate','description':'Evaluate one candidate STEP against a reference and frozen annotations. Returns a job_id; poll status, then results.',
     'inputSchema':object_schema({'candidate':STRING,'gt':STRING,'annotations':STRING,'case':STRING,
                                 'protocol':PROTOCOL_SCHEMA,'coordinate_mode':COORDINATE_SCHEMA},('candidate','gt','annotations'))},
    {'name':'status','description':'Read a job state, or list jobs submitted in this server session.',
     'inputSchema':object_schema({'job_id':STRING})},
    {'name':'results','description':'Read the complete final summary and paths to all persisted evidence for a finished job.',
     'inputSchema':object_schema({'job_id':STRING},('job_id',))},
    {'name':'capabilities','description':'Read the scoring protocol, fixed weights, configured input/output boundaries, and execution limits.',
     'inputSchema':object_schema({})},
]


class Service:
    def __init__(self, config_path):
        config_path = Path(config_path).resolve(strict=True)
        config = read_json(config_path)
        allowed = {'allowed_input_roots','output_root','python','timeout_seconds','max_active_jobs','protocol','coordinate_mode'}
        if not isinstance(config,dict) or set(config)-allowed:
            raise ValueError('configuration must be an object with documented keys only')
        self.protocol, self.coordinate_mode = scoring_options(config)

        def configured_path(value):
            if not isinstance(value,str) or not value:
                raise ValueError('configured paths must be nonempty strings')
            path = Path(value)
            return (path if path.is_absolute() else config_path.parent/path).resolve()

        roots = config.get('allowed_input_roots')
        if not isinstance(roots,list) or not roots:
            raise ValueError('allowed_input_roots must be a nonempty list')
        self.input_roots = [configured_path(p) for p in roots]
        if not all(p.is_dir() for p in self.input_roots):
            raise ValueError('every allowed input root must be an existing directory')
        self.output_root = configured_path(config.get('output_root'))
        self.python = configured_path(config.get('python',sys.executable))
        if not self.python.is_file():
            raise ValueError('configured Python executable does not exist')
        self.timeout = config.get('timeout_seconds',600)
        if isinstance(self.timeout,bool) or not isinstance(self.timeout,(float,int)) or not math.isfinite(self.timeout) or self.timeout<=0:
            raise ValueError('timeout_seconds must be finite and positive')
        self.max_jobs = config.get('max_active_jobs',1)
        if type(self.max_jobs) is not int or not 1<=self.max_jobs<=4:
            raise ValueError('max_active_jobs must be an integer from 1 to 4')
        self.output_root.mkdir(parents=True,exist_ok=True)
        self.jobs = {}
        self.lock = threading.RLock()
        self.threads = []

    def input_path(self, value, role):
        if not isinstance(value,str) or not Path(value).is_absolute():
            raise ValueError(role+' must be an absolute file path')
        path = Path(value).resolve(strict=True)
        if not path.is_file() or not any(path.is_relative_to(root) for root in self.input_roots):
            raise ValueError(role+' must be a file inside an allowed input root')
        suffixes = ('.json',) if role=='annotations' else ('.step','.stp')
        if path.suffix.lower() not in suffixes:
            raise ValueError(role+' has an unsupported file extension')
        return path

    def capabilities(self):
        is_v4 = self.protocol == PROTOCOL
        return {'protocol_id':self.protocol,'ranking_eligible':False,
            'supported_protocols':list(SUPPORTED_PROTOCOLS), 'coordinate_mode':self.coordinate_mode,
            'supported_coordinate_modes':['geometry','strict'] if is_v4 else ['strict'],
            'weights':read_json(BASE/('weights_v4.json' if is_v4 else 'weights_v3.json'))['weights'],
            'scored_metrics':['shape','dimension','mass'] if is_v4 else ['shape','dimension','distance','mass','face_match','section'],
            'diagnostic_metrics':['distance','face_match','section'] if is_v4 else [],
            'coordinate_frame':'rigid_aligned_mm' if self.coordinate_mode=='geometry' else 'fixed_world_mm','transport':'stdio',
            'allowed_input_roots':[str(p) for p in self.input_roots],
            'output_root':str(self.output_root),'python':str(self.python),
            'timeout_seconds':self.timeout,'max_active_jobs':self.max_jobs,
            'job_scope':'current server session; evidence persists on disk',
            'input_contract':'candidate STEP, GT STEP, frozen annotations bound to GT SHA256',
            'score_policy':'validation passed and integrity verified; unavailable measurements award zero with explicit policy_lower_bound'}

    def evaluate(self, arguments):
        options = {'protocol':arguments.get('protocol', self.protocol)}
        if 'coordinate_mode' in arguments:
            options['coordinate_mode'] = arguments['coordinate_mode']
        elif options['protocol'] == self.protocol:
            options['coordinate_mode'] = self.coordinate_mode
        protocol, coordinate_mode = scoring_options(options)
        case = arguments.get('case','case')
        if not isinstance(case,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',case):
            raise ValueError('case must be 1-64 letters, digits, underscore or hyphen, starting with a letter or digit')
        inputs = {role:self.input_path(arguments.get(role),role) for role in ('candidate','gt','annotations')}
        hashes = {role:sha(path) for role,path in inputs.items()}
        ann = read_json(inputs['annotations'])
        if not isinstance(ann,dict) or ann.get('gt_sha256')!=hashes['gt']:
            raise ValueError('annotations gt_sha256 does not match reference bytes')
        if sha(inputs['annotations'])!=hashes['annotations']:
            raise ValueError('annotations changed while validating inputs')
        with self.lock:
            if sum(j['state'] in ('queued','running') for j in self.jobs.values())>=self.max_jobs:
                raise ValueError('active job limit reached; poll status before submitting again')
            job_id = 'job-'+uuid.uuid4().hex
            folder = self.output_root/job_id
            folder.mkdir(exist_ok=False)
            write_json(folder/'cases.json',{'cases':[{'case':case,**{r:str(p) for r,p in inputs.items()},'expected_hashes':hashes}]})
            job = {'job_id':job_id,'case':case,'state':'queued','submitted_at':time.time(),
                   'protocol_id':protocol,'coordinate_mode':coordinate_mode,
                   'job_directory':str(folder),'output_directory':str(folder/'evaluation')}
            self.jobs[job_id] = job
            write_json(folder/'job_status.json',job)
            thread = threading.Thread(target=self.run_job,args=(job_id,),name=job_id)
            self.threads.append(thread)
            thread.start()
            return dict(job)

    def update(self, job_id, **changes):
        with self.lock:
            job = self.jobs[job_id]
            job.update(changes)
            write_json(Path(job['job_directory'])/'job_status.json',job)

    def run_job(self, job_id):
        job = self.jobs[job_id]
        folder = Path(job['job_directory'])
        try:
            self.update(job_id,state='running',started_at=time.time())
            options = {'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {'start_new_session':True}
            with (folder/'evaluator.log').open('w',encoding='utf-8') as log:
                env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1')
                command = [str(self.python),'-B',str(BASE/'evaluate.py'),
                    '--cases',str(folder/'cases.json'),'--output',job['output_directory'],
                    '--protocol',job['protocol_id'],'--timeout',str(self.timeout),'--workers','1']
                if job['protocol_id'] == PROTOCOL:
                    command += ['--coordinate-mode',job['coordinate_mode']]
                proc = subprocess.Popen(command,
                    stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,cwd=BASE,env=env,**options)
                timed_out = False
                try:
                    returncode = proc.wait(timeout=self.timeout+60)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    if os.name=='nt':
                        subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True,check=False)
                    else:
                        os.killpg(proc.pid,signal.SIGKILL)
                    returncode = proc.wait(timeout=10)
            summary_path = Path(job['output_directory'])/'summary.json'
            summary = read_json(summary_path) if summary_path.is_file() else None
            completed = (not timed_out and returncode==0 and isinstance(summary,dict)
                         and summary.get('protocol_id')==job['protocol_id']
                         and (job['protocol_id'] != PROTOCOL or summary.get('coordinate_mode')==job['coordinate_mode']))
            self.update(job_id,state='completed' if completed else 'failed',returncode=returncode,
                        timed_out=timed_out,finished_at=time.time(),summary_available=isinstance(summary,dict))
        except Exception as exc:
            self.update(job_id,state='failed',finished_at=time.time(),error=str(exc))

    def get_job(self, job_id):
        if not isinstance(job_id,str) or job_id not in self.jobs:
            raise ValueError('unknown job_id in this server session')
        return dict(self.jobs[job_id])

    def status(self, arguments):
        with self.lock:
            return self.get_job(arguments['job_id']) if 'job_id' in arguments else {'jobs':[dict(j) for j in self.jobs.values()]}

    def results(self, arguments):
        job = self.status(arguments)
        if job['state'] in ('queued','running'):
            raise ValueError('job is not finished; poll status')
        folder = Path(job['output_directory'])
        paths = {'summary':folder/'summary.json','manifest':folder/'manifest.json',
            'report':folder/'report.md','comparison':folder/'comparison.csv',
            'aggregate':folder/job['case']/'aggregate.json',
            'log':Path(job['job_directory'])/'evaluator.log',
            'status':Path(job['job_directory'])/'job_status.json'}
        return {'job':job,'summary':read_json(paths['summary']) if paths['summary'].is_file() else None,
                'files':{name:str(path) for name,path in paths.items() if path.is_file()}}

    def call_tool(self, name, arguments):
        tool = next((t for t in TOOLS if t['name']==name),None)
        if tool is None:
            raise ValueError('unknown tool')
        schema = tool['inputSchema']
        if set(arguments)-schema['properties'].keys() or set(schema['required'])-arguments.keys():
            raise ValueError('unexpected or missing tool arguments')
        if any(not isinstance(v,str) or not v for v in arguments.values()):
            raise ValueError('tool arguments must be nonempty strings')
        for key,value in arguments.items():
            choices = schema['properties'][key].get('enum')
            if choices is not None and value not in choices:
                raise ValueError('unsupported '+key)
        if name=='capabilities':
            return self.capabilities()
        return getattr(self,name)(arguments)

    def finish(self):
        # Keep a normal client disconnect from abandoning a partial run.
        # Each thread has a hard subprocess timeout in addition to worker limits.
        for thread in self.threads:
            thread.join()


def error(request_id, code, message):
    return {'jsonrpc':'2.0','id':request_id,'error':{'code':code,'message':message}}


def serve(service, incoming, outgoing):
    initialized = False
    while True:
        raw = incoming.readline(MAX_MESSAGE+1)
        if not raw:
            break
        if len(raw)>MAX_MESSAGE:
            response = error(None,-32600,'message exceeds 1 MiB limit; session closing')
            outgoing.write(json.dumps(response)+'\n')
            outgoing.flush()
            break
        try:
            request = json.loads(raw,parse_constant=lambda value: (_ for _ in ()).throw(ValueError('non-finite JSON value')))
        except (ValueError,UnicodeError):
            response = error(None,-32700,'invalid JSON')
        else:
            if not isinstance(request,dict) or request.get('jsonrpc')!='2.0' or not isinstance(request.get('method'),str):
                response = error(None,-32600,'invalid JSON-RPC request')
            elif 'id' not in request:
                continue
            elif type(request['id']) not in (str,int):
                response = error(None,-32600,'request id must be a string or integer')
            else:
                request_id = request['id']
                method = request['method']
                params = request.get('params',{})
                response = None
                if not isinstance(params,dict):
                    response = error(request_id,-32602,'params must be an object')
                elif method=='initialize':
                    version = params.get('protocolVersion')
                    result = {'protocolVersion':version if version in MCP_VERSIONS else MCP_VERSIONS[0],
                        'capabilities':{'tools':{'listChanged':False}},
                        'serverInfo':{'name':'fusion-step-evaluator','version':'1.0.0'},
                        'instructions':'Trusted local evaluation service. Submit frozen STEP inputs, poll status, then inspect results and coverage.'}
                    initialized = True
                elif method=='ping':
                    result = {}
                elif not initialized:
                    response = error(request_id,-32002,'initialize first')
                elif method=='tools/list':
                    result = {'tools':TOOLS}
                elif method=='tools/call':
                    arguments = params.get('arguments',{})
                    if not isinstance(arguments,dict) or not isinstance(params.get('name'),str):
                        response = error(request_id,-32602,'tools/call requires name and object arguments')
                    else:
                        try:
                            data = service.call_tool(params['name'],arguments)
                            result = {'content':[{'type':'text','text':json.dumps(data,ensure_ascii=False,allow_nan=False)}],
                                      'structuredContent':data,'isError':False}
                        except (ValueError,OSError,TypeError) as exc:
                            result = {'content':[{'type':'text','text':str(exc)}],'isError':True}
                else:
                    response = error(request_id,-32601,'method not found')
                if response is None:
                    response = {'jsonrpc':'2.0','id':request_id,'result':result}
        # Escape all non-ASCII code points so even a lone surrogate in an echoed
        # JSON-RPC id remains JSON data instead of crashing UTF-8 stdout encoding.
        outgoing.write(json.dumps(response,ensure_ascii=True,allow_nan=False)+'\n')
        outgoing.flush()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    args = parser.parse_args()
    for stream in (sys.stdin,sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    try:
        service = Service(args.config)
    except (ValueError,OSError,TypeError) as exc:
        print('Configuration error: '+str(exc),file=sys.stderr)
        return 2
    try:
        serve(service,sys.stdin,sys.stdout)
    finally:
        service.finish()
    return 0


if __name__=='__main__':
    raise SystemExit(main())
