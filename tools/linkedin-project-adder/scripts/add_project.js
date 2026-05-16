#!/usr/bin/env node
/**
 * Automates adding a project to LinkedIn's Projects section.
 * Uses a persistent browser profile so login is only needed once.
 *
 * Usage: node add_project.js '<json>'
 */

const { chromium } = require('./node_modules/playwright');
const os = require('os');
const path = require('path');

async function fillTypeahead(page, inputLocator, value) {
  await inputLocator.fill(value);
  await page.waitForTimeout(1200);
  const suggestion = page.locator('[role="option"], [role="listbox"] li').first();
  const hasSuggestion = await suggestion.isVisible({ timeout: 2000 }).catch(() => false);
  if (hasSuggestion) {
    await suggestion.click();
    await page.waitForTimeout(400);
    return true;
  }
  // Fallback: try pressing Enter
  await inputLocator.press('Enter');
  await page.waitForTimeout(400);
  return false;
}

async function run() {
  let data;
  try {
    data = JSON.parse(process.argv[2]);
  } catch (e) {
    console.error('Invalid JSON argument:', e.message);
    process.exit(1);
  }

  const skills = Array.isArray(data.skills) ? data.skills : [];
  const contributors = Array.isArray(data.contributors) ? data.contributors : [];

  const profileDir = path.join(os.homedir(), '.claude', 'linkedin-browser-profile');
  console.log('Launching browser...');

  const context = await chromium.launchPersistentContext(profileDir, {
    headless: false,
    viewport: { width: 1280, height: 900 },
    args: ['--no-sandbox'],
  });

  await context.addInitScript(() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
  });

  const page = await context.newPage();

  try {
    await page.goto('https://www.linkedin.com/in/me/', { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForTimeout(4000);

    // Check login
    const onLogin = page.url().includes('/login') || page.url().includes('/authwall');
    if (onLogin) {
      console.log('Please log in to LinkedIn in the browser window (up to 2 minutes)...');
      await page.waitForFunction(
        () => !window.location.href.includes('/login') && !window.location.href.includes('/authwall'),
        { timeout: 120000 }
      );
      await page.waitForTimeout(3000);
    }

    // Scroll to lazy-load the Projects section
    console.log('Scrolling to Projects section...');
    for (let y = 500; y <= 4000; y += 500) {
      await page.evaluate(pos => {
        const ws = document.getElementById('workspace');
        if (ws) ws.scrollTop = pos;
      }, y);
      await page.waitForTimeout(500);
    }
    await page.waitForTimeout(2000);

    // Click the Add a new project button
    const addBtn = await page.evaluate(() => {
      const el = document.querySelector('[aria-label="Add a new project"]');
      if (el) { el.scrollIntoView({ block: 'center' }); return true; }
      return false;
    });

    if (!addBtn) {
      console.error('Could not find the "Add a new project" button.');
      console.error('Please add the project manually using the content above.');
      await context.waitForEvent('close', { timeout: 300000 }).catch(() => {});
      process.exit(2);
    }

    await page.waitForTimeout(500);
    await page.locator('[aria-label="Add a new project"]').first().click();
    await page.waitForURL('**/edit/forms/project**', { timeout: 10000 });
    await page.locator('textarea[aria-label*="Description"]').waitFor({ timeout: 15000 });
    console.log('Form opened.');

    // --- Project name ---
    console.log('Filling project name...');
    const titleInput = page.locator('[role="dialog"] input[type="text"], input[id*=":r"]').first();
    await titleInput.fill(data.title);
    await page.waitForTimeout(300);

    // --- Description ---
    console.log('Filling description...');
    await page.locator('textarea[aria-label*="Description"]').fill(data.description);
    await page.waitForTimeout(300);

    // Scroll modal to reveal lower fields
    await page.evaluate(() => {
      const m = document.querySelector('[role="dialog"]');
      if (m) m.scrollTop = 600;
    });
    await page.waitForTimeout(1500);

    // --- Currently working checkbox ---
    if (data.currentlyWorking) {
      console.log('Checking "currently working"...');
      const cb = page.locator('[role="dialog"]').getByLabel(/currently working/i);
      const hasCb = await cb.isVisible({ timeout: 3000 }).catch(() => false);
      if (hasCb) {
        const isChecked = await cb.isChecked().catch(() => false);
        if (!isChecked) await cb.click();
      }
      await page.waitForTimeout(300);
    }

    // --- Dates ---
    console.log('Filling dates...');
    const allSelects = await page.locator('[role="dialog"] select').all();
    for (const sel of allSelects) {
      const opts = await sel.locator('option').allInnerTexts();
      const isMonthSelect = opts.some(o => /^January|^February|^March/i.test(o));
      const hasValue = await sel.evaluate(s => s.value);
      if (isMonthSelect && hasValue === '' && data.startMonth) {
        await sel.selectOption({ label: data.startMonth }).catch(() => {});
        await page.waitForTimeout(200);
        break;
      }
    }

    await page.waitForTimeout(500);
    const selects2 = await page.locator('[role="dialog"] select').all();
    let monthsFilled = 0;
    let yearsFilled = 0;
    for (const sel of selects2) {
      const opts = await sel.locator('option').allInnerTexts();
      const val = await sel.evaluate(s => s.value);
      const isMonth = opts.some(o => /^January|^February|^March/i.test(o));
      const isYear = opts.some(o => /^\d{4}$/.test(o.trim()));

      if (isMonth && val === '' && monthsFilled === 0 && data.startMonth) {
        await sel.selectOption({ label: data.startMonth }).catch(() => {});
        monthsFilled++;
        await page.waitForTimeout(200);
      } else if (isYear && val === '' && yearsFilled === 0 && data.startYear) {
        await sel.selectOption({ label: data.startYear }).catch(() => {});
        yearsFilled++;
        await page.waitForTimeout(200);
      } else if (isMonth && val === '' && monthsFilled === 1 && !data.currentlyWorking && data.endMonth) {
        await sel.selectOption({ label: data.endMonth }).catch(() => {});
        monthsFilled++;
        await page.waitForTimeout(200);
      } else if (isYear && val === '' && yearsFilled === 1 && !data.currentlyWorking && data.endYear) {
        await sel.selectOption({ label: data.endYear }).catch(() => {});
        yearsFilled++;
        await page.waitForTimeout(200);
      }
    }

    // --- URL ---
    if (data.url) {
      console.log('Filling URL...');
      const urlInput = page.locator('[role="dialog"] input[type="text"], [role="dialog"] input[type="url"]')
        .filter({ hasNot: page.locator('[aria-label*="project" i], [aria-label*="name" i]') })
        .last();
      const hasUrl = await urlInput.isVisible({ timeout: 2000 }).catch(() => false);
      if (hasUrl) {
        await urlInput.fill(data.url).catch(() => {});
        await page.waitForTimeout(200);
      }
    }

    // --- Associated with ---
    if (data.associatedWith) {
      console.log('Filling "associated with"...');
      try {
        const assocInput = page.locator('[role="dialog"]').locator(
          'input[aria-label*="associated" i], input[placeholder*="company" i], input[placeholder*="organization" i], input[placeholder*="school" i]'
        ).first();
        const visible = await assocInput.isVisible({ timeout: 2000 }).catch(() => false);
        if (visible) {
          await fillTypeahead(page, assocInput, data.associatedWith);
        } else {
          console.log('Could not find "associated with" input — skipping.');
        }
      } catch (e) {
        console.log(`Could not fill "associated with": ${e.message}`);
      }
    }

    // Scroll further to reveal skills / contributors
    await page.evaluate(() => {
      const m = document.querySelector('[role="dialog"]');
      if (m) m.scrollTop = 1200;
    });
    await page.waitForTimeout(1000);

    // --- Skills ---
    if (skills.length > 0) {
      console.log('Adding skills...');
      for (const skill of skills.slice(0, 5)) {
        try {
          const skillInput = page.locator('[role="dialog"]').locator(
            'input[aria-label*="skill" i], input[placeholder*="skill" i], input[aria-label*="Add skill" i]'
          ).first();
          const visible = await skillInput.isVisible({ timeout: 2000 }).catch(() => false);
          if (visible) {
            const found = await fillTypeahead(page, skillInput, skill);
            if (!found) {
              console.log(`Skill "${skill}" not found in LinkedIn's ontology — mention it in description instead.`);
            } else {
              console.log(`Added skill: ${skill}`);
            }
          } else {
            console.log(`Skills input not found — could not add "${skill}".`);
            break;
          }
        } catch (e) {
          console.log(`Could not add skill "${skill}": ${e.message}`);
        }
      }
    }

    // --- Contributors ---
    if (contributors.length > 0) {
      console.log('Adding contributors...');
      for (const contributor of contributors) {
        try {
          const contribInput = page.locator('[role="dialog"]').locator(
            'input[aria-label*="contributor" i], input[aria-label*="collaborator" i], input[placeholder*="contributor" i], input[placeholder*="collaborator" i], input[placeholder*="member" i]'
          ).first();
          const visible = await contribInput.isVisible({ timeout: 2000 }).catch(() => false);
          if (visible) {
            const found = await fillTypeahead(page, contribInput, contributor);
            if (!found) {
              console.log(`Contributor "${contributor}" not found — add them manually.`);
            } else {
              console.log(`Added contributor: ${contributor}`);
            }
          } else {
            console.log(`Contributors input not found — could not add "${contributor}".`);
            break;
          }
        } catch (e) {
          console.log(`Could not add contributor "${contributor}": ${e.message}`);
        }
      }
    }

    console.log('\nAll fields filled. Review the form in the browser and click Save when ready.');
    console.log('(Close the browser after saving to finish.)');

    await context.waitForEvent('close', { timeout: 300000 });
    console.log('Done.');

  } catch (err) {
    console.error('Error:', err.message);
    console.error('Browser left open — complete the form manually if needed.');
    await context.waitForEvent('close', { timeout: 300000 }).catch(() => {});
    process.exit(1);
  }
}

run().catch(err => {
  console.error('Fatal:', err.message);
  process.exit(1);
});
