const fs = require('fs');
const path = 'src/pages/CssStockTracking.jsx';
let text = fs.readFileSync(path, 'utf8');
text = text.replace('hint={SUM(Order Form CURRENTQUANTITY)\\}', 'hint={\SUM(Order Form CURRENTQUANTITY)\\}');
fs.writeFileSync(path, text);
