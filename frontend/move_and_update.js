const fs = require('fs');
const path = require('path');

function updateImports(filePath) {
    if (!fs.existsSync(filePath)) return;
    
    if (fs.statSync(filePath).isDirectory()) {
        const files = fs.readdirSync(filePath);
        for (const file of files) {
            updateImports(path.join(filePath, file));
        }
        return;
    }

    if (!filePath.endsWith('.js') && !filePath.endsWith('.jsx')) return;

    let content = fs.readFileSync(filePath, 'utf8');
    let changed = false;

    // We only want to match imports like: import ... from '../xxx' or import '../xxx'
    // Regex matches require or import strings starting with ../ or ../../ etc.
    const importRegex = /(from\s+['"])((\.\.\/)+)([^'"]+['"])/g;
    const directImportRegex = /(import\s+['"])((\.\.\/)+)([^'"]+['"])/g;
    
    const replacer = (match, p1, p2, p3, p4) => {
        changed = true;
        return p1 + '../' + p2 + p4;
    };

    content = content.replace(importRegex, replacer);
    content = content.replace(directImportRegex, replacer);

    if (changed) {
        fs.writeFileSync(filePath, content, 'utf8');
        console.log('Updated imports in:', filePath);
    }
}

// Ensure target directories exist
fs.mkdirSync('./src/pages/infrastructure/clusters', { recursive: true });
fs.mkdirSync('./src/pages/infrastructure/hibernation', { recursive: true });

// Move folders
try {
    // move contents of src/components/clusters to src/pages/infrastructure/clusters
    if (fs.existsSync('./src/components/clusters')) {
        const items = fs.readdirSync('./src/components/clusters');
        for (const item of items) {
            fs.renameSync(
                path.join('./src/components/clusters', item),
                path.join('./src/pages/infrastructure/clusters', item)
            );
        }
        fs.rmdirSync('./src/components/clusters');
        console.log('Moved clusters folder');
        updateImports('./src/pages/infrastructure/clusters');
    }
} catch (e) { console.error('Error moving clusters:', e); }

try {
    // move contents of src/components/hibernation to src/pages/infrastructure/hibernation
    if (fs.existsSync('./src/components/hibernation')) {
        const items = fs.readdirSync('./src/components/hibernation');
        for (const item of items) {
            fs.renameSync(
                path.join('./src/components/hibernation', item),
                path.join('./src/pages/infrastructure/hibernation', item)
            );
        }
        fs.rmdirSync('./src/components/hibernation');
        console.log('Moved hibernation folder');
        updateImports('./src/pages/infrastructure/hibernation');
    }
} catch (e) { console.error('Error moving hibernation:', e); }

