const fs = require('fs');
const file = 'src/pages/StoreMaster.jsx';
let code = fs.readFileSync(file, 'utf8');

const regex = /<PageHeader[\s\S]*?\/>/;
const replacement = '<PageHeader\n        title="Store Master"\n        description="Centralized retail directory. Store statuses are derived automatically; metadata is fully editable."\n        actions={<ExportButton onExport={() => storeMasterApi.export(filters, search)} />}\n      />';

code = code.replace(regex, replacement);

fs.writeFileSync(file, code);
