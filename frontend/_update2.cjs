const fs = require('fs');
const path = 'src/pages/CssStockTracking.jsx';
const lines = fs.readFileSync(path, 'utf8').split('\n');
const fixedLines = lines.map(l => {
  if (l.includes('hint={SUM(Order Form CURRENTQUANTITY)\\}')) {
    return '                hint={\SUM(Order Form CURRENTQUANTITY)\\}';
  }
  return l;
});
fs.writeFileSync(path, fixedLines.join('\n'));
