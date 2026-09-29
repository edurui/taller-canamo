// Syntax-only fallback. Does NOT replace npm run typecheck or a Vite build.
const fs = require('fs');
const path = require('path');
const cp = require('child_process');
let ts;
try { ts = require('typescript'); }
catch { ts = require(path.join(cp.execSync('npm root -g', {encoding:'utf8'}).trim(), 'typescript')); }
let errors = [];
const root = path.resolve(__dirname, '..');
const files = fs.readdirSync(path.join(root,'frontend')).filter(f=>f.endsWith('.tsx'));
for (const file of files) {
  const result=ts.transpileModule(fs.readFileSync(path.join(root,'frontend',file),'utf8'), {
    fileName:file, reportDiagnostics:true,
    compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext,jsx:ts.JsxEmit.ReactJSX}
  });
  for (const item of result.diagnostics || []) if (item.category===ts.DiagnosticCategory.Error) {
    errors.push(file+': '+ts.flattenDiagnosticMessageText(item.messageText,' '));
  }
}
console.log(JSON.stringify({typescript:ts.version,files:files.length,syntaxErrors:errors,
  note:'Transpilation/syntax only. React typings, bundling and browser execution NOT verified.'},null,2));
process.exitCode=errors.length?1:0;
