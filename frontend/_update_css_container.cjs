const fs = require('fs');
const path = 'src/pages/CssStockTracking.jsx';
let text = fs.readFileSync(path, 'utf8');

text = text.replace(
  '<div className="flex-1 flex items-center justify-center mt-6">',
  '<div className="flex-1 flex items-center justify-center mt-12 mb-4">'
);
text = text.replace(
  'border-border shadow-sm bg-gradient-to-br from-card to-card-hover relative overflow-hidden',
  'border-border shadow-sm bg-gradient-to-b from-card/80 to-card hover:bg-card-hover transition-colors relative overflow-hidden h-[240px] flex flex-col justify-end'
);

fs.writeFileSync(path, text);
