const fs = require('fs');
const file = 'src/pages/CssStockTracking.jsx';
let code = fs.readFileSync(file, 'utf8');

// Remove eyebrow and description from PageHeader
code = code.replace(/eyebrow="[^"]*"\s*/g, '');
code = code.replace(/description="[^"]*"\s*/g, '');

// Remove hint attributes from KpiCards
code = code.replace(/hint=\{[^}]+\}\s*/g, '');
code = code.replace(/hint="[^"]*"\s*/g, '');

fs.writeFileSync(file, code);
