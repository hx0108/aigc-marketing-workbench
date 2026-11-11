const fs=require('fs'),b=require('./vendor/babel.js');
try{const src=['shared.jsx','flow.jsx'].map(n=>fs.readFileSync(__dirname+'/'+n,'utf8')).join('\n');fs.writeFileSync(__dirname+'/app.compiled.js',b.transform(src,{presets:['react'],comments:false}).code);console.log('React JSX 编译通过')}catch(e){console.error(e.message);process.exitCode=1}
