/**
 * Utility functions to fix common code issues
 */

/**
 * Fix Flask code to use render_template_string instead of render_template
 * @param {string} code - The code to fix
 * @returns {string} - Fixed code
 */
export function fixFlaskTemplates(code) {
  if (!code || typeof code !== 'string') return code;
  
  // Check if this is Flask code
  if (!code.includes('from flask import') && !code.includes('import flask')) {
    return code;
  }
  
  let fixedCode = code;
  
  // Add render_template_string to imports if not present
  if (!fixedCode.includes('render_template_string')) {
    fixedCode = fixedCode.replace(
      /from flask import/,
      'from flask import render_template_string,'
    );
    // Remove duplicate if it was added
    fixedCode = fixedCode.replace(
      /render_template_string,render_template_string,/g,
      'render_template_string,'
    );
  }
  
  // Replace render_template( with render_template_string(
  // But only if it's not already render_template_string
  fixedCode = fixedCode.replace(
    /\brender_template\((?!_string)/g,
    'render_template_string('
  );
  
  return fixedCode;
}

/**
 * Remove integrity and crossorigin attributes from CDN links
 * @param {string} code - The code to fix
 * @returns {string} - Fixed code
 */
export function fixCDNIntegrity(code) {
  if (!code || typeof code !== 'string') return code;
  
  let fixedCode = code;
  
  // Remove integrity attributes
  fixedCode = fixedCode.replace(/\s+integrity="[^"]*"/g, '');
  fixedCode = fixedCode.replace(/\s+integrity='[^']*'/g, '');
  
  // Remove crossorigin attributes
  fixedCode = fixedCode.replace(/\s+crossorigin="[^"]*"/g, '');
  fixedCode = fixedCode.replace(/\s+crossorigin='[^']*'/g, '');
  fixedCode = fixedCode.replace(/\s+crossorigin(?=\s|>)/g, '');
  
  return fixedCode;
}

/**
 * Apply all code fixes
 * @param {string} code - The code to fix
 * @returns {string} - Fixed code
 */
export function applyAllFixes(code) {
  if (!code || typeof code !== 'string') return code;
  
  let fixedCode = code;
  fixedCode = fixFlaskTemplates(fixedCode);
  fixedCode = fixCDNIntegrity(fixedCode);
  
  return fixedCode;
}
