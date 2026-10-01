const fs = require('fs');
const file = 'src/pages/StoreMaster.jsx';
let code = fs.readFileSync(file, 'utf8');

const regex = /<PageHeader[\s\S]*?\/>/;
const replacement = \<PageHeader title="Store Master" description="Centralized retail directory. Store statuses are derived automatically; metadata is fully editable." actions={<ExportButton onExport={() => storeMasterApi.export(filters, search)} />} />\;

code = code.replace(regex, replacement);

fs.writeFileSync(file, code);
