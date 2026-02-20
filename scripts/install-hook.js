#!/usr/bin/env node
/**
 * Claude Code Hook 자동 설치 스크립트
 *
 * Claude Code의 settings.json에 PreToolUse 훅을 추가합니다.
 */

const fs = require('fs');
const path = require('path');
const os = require('os');

// Claude Code 설정 파일 경로
const SETTINGS_PATHS = [
  // macOS
  path.join(os.homedir(), 'Library', 'Application Support', 'claude-code', 'settings.json'),
  // Linux
  path.join(os.homedir(), '.config', 'claude-code', 'settings.json'),
  // Windows
  path.join(os.homedir(), 'AppData', 'Roaming', 'claude-code', 'settings.json'),
  // 글로벌 Claude Code 설정 (일반적인 경로)
  path.join(os.homedir(), '.claude', 'settings.json'),
];

const HOOK_SCRIPT = path.resolve(__dirname, 'claude-code-hook.js');

function findSettingsFile() {
  for (const p of SETTINGS_PATHS) {
    if (fs.existsSync(p)) {
      return p;
    }
  }
  // 설정 파일이 없으면 ~/.claude/settings.json 생성
  const defaultPath = path.join(os.homedir(), '.claude', 'settings.json');
  const dir = path.dirname(defaultPath);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
  return defaultPath;
}

function install() {
  const settingsPath = findSettingsFile();
  console.log(`설정 파일: ${settingsPath}`);

  let settings = {};
  if (fs.existsSync(settingsPath)) {
    try {
      settings = JSON.parse(fs.readFileSync(settingsPath, 'utf-8'));
    } catch (e) {
      console.error('설정 파일 파싱 오류:', e.message);
      settings = {};
    }
  }

  // hooks 구조 초기화
  if (!settings.hooks) settings.hooks = {};
  if (!settings.hooks.PreToolUse) settings.hooks.PreToolUse = [];

  // 이미 설치되어 있는지 확인
  const existing = settings.hooks.PreToolUse.find(
    (h) => h.hooks && h.hooks.some((hh) => hh.command && hh.command.includes('claude-code-hook'))
  );

  if (existing) {
    console.log('이미 설치되어 있습니다.');
    return;
  }

  // 훅 추가
  settings.hooks.PreToolUse.push({
    matcher: '',
    hooks: [
      {
        type: 'command',
        command: `node "${HOOK_SCRIPT}"`,
      },
    ],
  });

  fs.writeFileSync(settingsPath, JSON.stringify(settings, null, 2));
  console.log('');
  console.log('✓ Claude Code 훅이 설치되었습니다!');
  console.log(`  경로: ${settingsPath}`);
  console.log(`  스크립트: ${HOOK_SCRIPT}`);
  console.log('');
  console.log('Claude Code를 재시작하면 적용됩니다.');
}

function uninstall() {
  for (const settingsPath of SETTINGS_PATHS) {
    if (!fs.existsSync(settingsPath)) continue;

    try {
      const settings = JSON.parse(fs.readFileSync(settingsPath, 'utf-8'));
      if (settings.hooks && settings.hooks.PreToolUse) {
        settings.hooks.PreToolUse = settings.hooks.PreToolUse.filter(
          (h) => !(h.hooks && h.hooks.some((hh) => hh.command && hh.command.includes('claude-code-hook')))
        );
        fs.writeFileSync(settingsPath, JSON.stringify(settings, null, 2));
        console.log(`✓ 훅이 제거되었습니다: ${settingsPath}`);
      }
    } catch (e) {
      console.error(`설정 파일 처리 오류 (${settingsPath}):`, e.message);
    }
  }
}

const action = process.argv[2] || 'install';
if (action === 'uninstall') {
  uninstall();
} else {
  install();
}
