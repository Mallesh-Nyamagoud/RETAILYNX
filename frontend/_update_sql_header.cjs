const fs = require('fs');
const file = 'src/pages/SqlPlatform.jsx';
let code = fs.readFileSync(file, 'utf8');

// Remove the description entirely to make it look clean and flagship
code = code.replace(/\s*description="Flagship-level SQL execution environment[^"]*"/, '');

fs.writeFileSync(file, code);
