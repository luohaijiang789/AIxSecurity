"""Real, bounded Java preparation: Git + isolated Maven + Semgrep CE AST/taint.

Only public GitHub HTTPS repositories are accepted in this first adapter. Rules
cover request-to-SQL, command and file I/O within one method, not whole-program data flow.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit
import uuid


# Both attempts run inside the same container and retain its isolated .m2 cache.
# The outer Docker timeout bounds both attempts together; TLS remains verified.
_MAVEN_RETRY_SCRIPT = """for attempt in 1 2; do
  echo "AIX_MAVEN_COMPILE_ATTEMPT=$attempt/2"
  if mvn -B -ntp -U -Daether.transport.http.retryHandler.count=2 -DskipTests compile; then
    echo "AIX_MAVEN_COMPILE_SUCCESS_ATTEMPT=$attempt"
    exit 0
  else
    code=$?
  fi
  echo "AIX_MAVEN_COMPILE_FAILED_ATTEMPT=$attempt EXIT=$code"
  if [ "$attempt" -eq 2 ]; then exit "$code"; fi
  sleep 2
done"""


class PreparationError(RuntimeError):
    """Preparation failed; local stage logs contain the diagnostic details."""


class JavaPreparer:
    def __init__(self, semgrep_path, image='maven:3.9-eclipse-temurin-17', *, progress=None,
                 cache_scope=None):
        self.semgrep_path = str(semgrep_path)
        self.image = image
        self.progress = progress or (lambda stage: None)
        self.cache_scope = str(Path(cache_scope or Path.cwd()).resolve())

    def _cache_volume(self, url, commit):
        # Application workspace, repo, revision and build configuration isolate
        # untrusted dependency caches. Retry job directories are intentionally
        # excluded so explicit retries retain already downloaded dependencies.
        scope = json.dumps([self.cache_scope, url, commit, self.image, _MAVEN_RETRY_SCRIPT])
        return 'aixsecurity-m2-' + hashlib.sha256(scope.encode()).hexdigest()[:40]

    def _run(self, args, *, cwd, env, timeout, log):
        try:
            with Path(log).open('w') as output:
                result = subprocess.run(args, cwd=cwd, env=env, stdout=output,
                                        stderr=subprocess.STDOUT, timeout=timeout, check=False)
            if result.returncode:
                raise PreparationError(f'Java preparation failed at {Path(log).stem}')
        except (OSError, subprocess.TimeoutExpired) as error:
            raise PreparationError(f'Java preparation failed at {Path(log).stem}') from error
        return Path(log).read_text(errors='replace')

    def prepare(self, url, workdir):
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or parsed.netloc != 'github.com' or
                parsed.query or parsed.fragment or
                not re.fullmatch(r'/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?', parsed.path)):
            raise PreparationError('Only public GitHub HTTPS repository URLs are supported')
        work = Path(workdir).resolve()
        work.mkdir(parents=True, exist_ok=True)
        repo = work / 'repository'
        if repo.exists():
            raise PreparationError('Preparation work directory already contains a repository')
        home = work / 'tool-home'
        home.mkdir(exist_ok=True)
        env = {key: value for key, value in os.environ.items()
               if key in ('PATH', 'SYSTEMROOT', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY',
                          'NO_PROXY', 'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy')}
        env.update(HOME=str(home), GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null',
                   GIT_TERMINAL_PROMPT='0', GIT_LFS_SKIP_SMUDGE='1',
                   SEMGREP_SEND_METRICS='off', SEMGREP_ENABLE_VERSION_CHECK='0')
        if Path('/etc/ssl/cert.pem').is_file():
            env['SSL_CERT_FILE'] = '/etc/ssl/cert.pem'
        self.progress('clone')
        self._run(['git', '-c', 'core.hooksPath=/dev/null', '-c', 'http.followRedirects=false',
                   '-c', 'protocol.file.allow=never', 'clone', '--depth', '1',
                   '--no-recurse-submodules', '--', url, str(repo)],
                  cwd=work, env=env, timeout=180, log=work/'clone.log')
        commit = self._run(['git', 'rev-parse', 'HEAD'], cwd=repo, env=env,
                           timeout=20, log=work/'commit.log').strip()
        if not re.fullmatch('[0-9a-f]{40}', commit) or not (repo/'pom.xml').is_file():
            raise PreparationError('A fixed Git commit and root Maven project are required')
        # Analysis never follows repository-controlled links out of the checkout.
        if any(path.is_symlink() for path in repo.rglob('*')):
            raise PreparationError('Repository symbolic links require an explicit preparation policy')
        self.progress('build')
        name = 'aixsecurity-build-' + uuid.uuid4().hex
        cache_volume = self._cache_volume(url, commit)
        # Do not forward host proxy/config/credentials into the container. Maven
        # dependency egress is enabled; no services are published to the host.
        command = ['docker', 'run', '--rm', '--name', name, '--read-only',
                   '--cap-drop=ALL', '--security-opt=no-new-privileges',
                   '--memory=3g', '--cpus=2', '--pids-limit=256',
                   '--mount', f'type=bind,src={repo},dst=/input,readonly',
                   '--tmpfs', '/work:rw,size=1g', '--tmpfs', '/tmp:rw,size=512m',
                   '--tmpfs', '/root/.m2:rw,size=16m',
                   '--mount', f'type=volume,src={cache_volume},dst=/root/.m2/repository',
                   '-w', '/work', self.image,
                   'sh', '-c', 'cp -R /input/. /work/ && ' + _MAVEN_RETRY_SCRIPT]
        # Docker uses its own configuration for daemon routing, not the isolated
        # Git/Semgrep HOME. It receives no model credentials through container env.
        docker_env = dict(env, HOME=os.path.expanduser('~'))
        try:
            self._run(command, cwd=work, env=docker_env, timeout=1200, log=work/'build.log')
        finally:
            try:
                subprocess.run(['docker', 'rm', '-f', name], env=docker_env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=30, check=False)
            except (OSError, subprocess.TimeoutExpired):
                pass  # Preserve the original build error; no success is inferred.
        self.progress('static_analysis')
        rules = Path(__file__).resolve().parents[1] / 'rules' / 'java.json'
        rules_digest = hashlib.sha256(rules.read_bytes()).hexdigest()
        report_path = work / 'semgrep.json'
        self._run([self.semgrep_path, 'scan', '--config', str(rules), '--json',
                   '--dataflow-traces', '--metrics=off', '--disable-version-check',
                   '--no-git-ignore', '--exclude', '.git', '--exclude', 'target',
                   '--max-target-bytes', '1000000', '--timeout', '10',
                   '--output', str(report_path), str(repo)],
                  cwd=work, env=env, timeout=600, log=work/'semgrep.log')
        if hashlib.sha256(rules.read_bytes()).hexdigest() != rules_digest:
            raise PreparationError('Analysis rules changed during preparation')
        try:
            report = json.loads(report_path.read_text())
        except (OSError, ValueError) as error:
            raise PreparationError('Semgrep did not produce a valid JSON report') from error
        errors = report.get('errors', [])
        if errors:
            raise PreparationError('Semgrep reported incomplete analysis; see semgrep.json')
        version = self._run([self.semgrep_path, '--version'], cwd=work, env=env,
                            timeout=30, log=work/'semgrep-version.log').strip()
        source_manifest = {str(path.relative_to(repo)): hashlib.sha256(path.read_bytes()).hexdigest()
                           for path in sorted(repo.rglob('*.java')) if path.is_file()}
        coverage = self._coverage(report, repo, source_manifest)
        assets, candidates = self._extract(report, repo, url, commit)
        self.progress('prepared')
        return {'commit': commit, 'repo_path': str(repo),
                'source_manifest': source_manifest, 'analysis_success': True,
                'capabilities': ['java-ast', 'java-sqli-intraprocedural',
                                 'java-command-injection-intraprocedural',
                                 'java-path-traversal-intraprocedural', 'maven-compile'],
                'assets': assets, 'candidates': candidates,
                'build': {'status': 'completed', 'success': True, 'image': self.image,
                          'log_path': str(work/'build.log'), 'goal': 'compile',
                          'max_compile_attempts': 2, 'transport_retry_count': 2,
                          'dependency_cache_volume': cache_volume},
                'tool_versions': {'semgrep': version,
                                  'rules_sha256': rules_digest},
                'analysis_metrics': {**coverage,
                                     'candidate_count': len(candidates),
                                     'asset_count': len(assets)},
                'limitations': [f"Java scan coverage: {coverage['scanned_java_files']}/{coverage['source_files']}; "
                                 f"{coverage['unscanned_java_files']} Java files unscanned, including "
                                 f"{len(coverage['unscanned_large_java_paths'])} over the 1000000-byte limit. "
                                 'See analysis_metrics for the explicit unscanned paths.',
                                'Semgrep CE intraprocedural SQLi, command-input and path-to-I/O candidates only; no cross-method/service proof.',
                                'Command rules cover Runtime.getRuntime().exec, typed Runtime receivers and directly started sh/bash -c ProcessBuilder; other builders/arrays/wrappers may be missed. Runtime.exec does not itself interpret shell metacharacters.',
                                'Path rules cover selected imported/fully qualified Java stream and Files I/O APIs with File/Path wrappers; normalization alone is not treated as a sanitizer, and confinement guards require independent review.',
                                'Guard assets are observations, not proof of effective sanitization.',
                                'Maven compile only; application is not deployed or dynamically tested.',
                                'Dependency-download network is enabled inside the bounded build container.',
                                'Per-workspace/repository/commit/build Docker dependency volume persists for retries; explicit retention cleanup is required.']}

    @staticmethod
    def _coverage(report, repo, source_manifest):
        if not source_manifest:
            raise PreparationError('Repository contains no Java source files')
        scanned = set()
        for item in report.get('paths', {}).get('scanned', []):
            path = Path(item)
            path = path if path.is_absolute() else repo / path
            try:
                relative = str(path.resolve().relative_to(repo.resolve()))
            except ValueError as error:
                raise PreparationError('Analyzer scanned a path outside the repository') from error
            if relative in source_manifest:
                scanned.add(relative)
        if not scanned:
            raise PreparationError('Analyzer scanned no Java source files')
        missing = sorted(set(source_manifest) - scanned)
        return {'scanned_files': len(report.get('paths', {}).get('scanned', [])),
                'source_files': len(source_manifest), 'scanned_java_files': len(scanned),
                'unscanned_java_files': len(missing), 'unscanned_java_paths': missing,
                'unscanned_large_java_paths': [p for p in missing
                                              if (repo / p).stat().st_size > 1000000]}

    @staticmethod
    def _extract(report, repo, repository_url, commit):
        assets, candidates = [], []
        for result in report.get('results', []):
            path = Path(result['path'])
            path = path if path.is_absolute() else repo / path
            try:
                relative = path.resolve().relative_to(repo.resolve())
            except ValueError as error:
                raise PreparationError('Analyzer returned a path outside the repository') from error
            start, end = result['start']['line'], result['end']['line']
            lines = path.read_text(errors='replace').splitlines()
            excerpt = '\n'.join(f'{n+1}: {lines[n]}' for n in range(max(0,start-16), min(len(lines),end+12)))
            rule_id = result['check_id']
            common = {'path': str(relative), 'start_line': start, 'end_line': end,
                      'rule_id': rule_id, 'code_excerpt': excerpt}
            if '.asset.' in rule_id:
                assets.append(dict(common, kind=rule_id.rsplit('.',1)[-1]))
            elif any(rule_id.endswith(f'aix.java.{category}.taint')
                     for category in ('sqli', 'command-injection', 'path-traversal')):
                category = next(category for category in ('sqli', 'command-injection', 'path-traversal')
                                if rule_id.endswith(f'aix.java.{category}.taint'))
                trace = result.get('extra', {}).get('dataflow_trace')
                candidates.append(dict(common,
                    id=hashlib.sha256(json.dumps([repository_url, commit, str(relative),
                                                start, rule_id]).encode()).hexdigest()[:20],
                    repository_url=repository_url, commit=commit, category=category,
                    message=result.get('extra',{}).get('message',f'{category} candidate'),
                    source=trace.get('taint_source') if isinstance(trace,dict) else None,
                    sink=trace.get('taint_sink') if isinstance(trace,dict) else None,
                    dataflow_trace=trace,
                    evidence={'engine':'semgrep-ce','mode':'taint','scope':'intraprocedural',
                              'raw_result':result}))
        return assets, candidates
