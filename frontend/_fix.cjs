const fs = require('fs');
const file = 'src/pages/StoreMaster.jsx';
let code = fs.readFileSync(file, 'utf8');

code = code.replace(/<PageHeader\n\s*title="Store Master"\n\s*description="Centralized retail directory. Store statuses are derived automatically; metadata is fully editable."\n\s*actions=\{<ExportButton onExport=\{\(\) => storeMasterApi\.export\(filters, search\)\} \/>\}\n\s*\/>\}\n\s*\/>/g, '<PageHeader\n        title="Store Master"\n        description="Centralized retail directory. Store statuses are derived automatically; metadata is fully editable."\n        actions={<ExportButton onExport={() => storeMasterApi.export(filters, search)} />}\n      />');

fs.writeFileSync(file, code);
