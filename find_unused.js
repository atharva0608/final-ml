const fs = require('fs');
const path = require('path');

const srcDir = path.join(__dirname, 'frontend', 'src');

function getAllFiles(dir, ext = '.jsx', fileList = []) {
  const files = fs.readdirSync(dir);
  for (const file of files) {
    const filePath = path.join(dir, file);
    if (fs.statSync(filePath).isDirectory()) {
      getAllFiles(filePath, ext, fileList);
    } else if (filePath.endsWith(ext) || filePath.endsWith('.js')) {
      fileList.push(filePath);
    }
  }
  return fileList;
}

const allFiles = getAllFiles(srcDir);
const jsxFiles = allFiles.filter(f => f.endsWith('.jsx'));
const unusedFiles = [];

for (const targetFile of jsxFiles) {
  // Get filename without extension and path relative to src
  const baseName = path.basename(targetFile, '.jsx');
  const dirName = path.basename(path.dirname(targetFile));
  
  let isUsed = false;
  for (const f of allFiles) {
    if (f === targetFile) continue;
    const content = fs.readFileSync(f, 'utf-8');
    // Simple heuristic: does any other file contain the basename?
    if (content.includes(baseName)) {
      isUsed = true;
      break;
    }
  }
  if (!isUsed) {
    unusedFiles.push(targetFile);
  }
}

console.log("Potentially unused JSX files:");
unusedFiles.forEach(f => console.log(f.replace(srcDir, '')));
