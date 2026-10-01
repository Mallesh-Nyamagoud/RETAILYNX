const fs = require('fs');
const path = 'src/components/common/GaugeChart.jsx';
let text = fs.readFileSync(path, 'utf8');

text = text.replace(
  '<circle cx={cx} cy={cy} r="10" className="fill-text-primary drop-shadow-sm" />\n        <circle cx={cx} cy={cy} r="3" className="fill-surface" />\n      </svg>\n\n      {/* Central Label */}\n      <div className="absolute bottom-4 flex flex-col items-center">\n        <span className="text-3xl font-extrabold text-text-primary tracking-tight tabular-nums">\n          {Number(value).toFixed(1)}%\n        </span>\n        <span className="text-[11px] font-bold text-text-secondary mt-0.5 uppercase tracking-widest">\n          {label}\n        </span>\n      </div>',
  '<circle cx={cx} cy={cy} r="14" className="fill-text-primary drop-shadow-md" />\n        <circle cx={cx} cy={cy} r="5" className="fill-surface" />\n      </svg>\n\n      {/* Central Label */}\n      <div className="absolute bottom-2 flex flex-col items-center">\n        <span className="text-5xl font-black text-text-primary tracking-tight tabular-nums drop-shadow-md">\n          {Number(value).toFixed(1)}%\n        </span>\n        <span className="text-xs font-bold text-text-secondary mt-2 uppercase tracking-[0.25em] drop-shadow-sm">\n          {label}\n        </span>\n      </div>'
);

text = text.replace('const cy = 160;', 'const cy = 190;');
text = text.replace('strokeWidth = 32;', 'strokeWidth = 46;');
text = text.replace('radius = 120;', 'radius = 150;');
text = text.replace('max-w-[360px]', 'max-w-[480px]');
text = text.replace('viewBox="0 0 400 210"', 'viewBox="0 0 400 280"');

fs.writeFileSync(path, text);
