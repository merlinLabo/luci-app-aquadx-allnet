'use strict';
'require fs';
'require poll';
'require ui';
'require view';

var stateNode;
var startButton;
var stopButton;
var openButton;
var exportButton;
var importButton;
var logNode;
var logDetails;
var progressNode;
var autoStartCheckbox;
var customServerAddressCheckbox;
var customServerAddressInput;
var machineRowsNode;
var redirectStateNode;
var redirectStatusRow;
var settingsDirty = false;
var clientsSnapshot = '';
var databaseBusy = false;
var lastState = { running: false, starting: false, enabled: false, port: 8088, redirectActive: false };

function readStatus() {
	return fs.exec_direct('/usr/libexec/aquadx-ctl', [ 'status' ]).then(function(output) {
		try {
			return JSON.parse(output);
		}
		catch (e) {
			return { running: false, starting: false, enabled: false, port: 8088, redirectActive: false };
		}
	});
}

function readClients() {
	return fs.exec_direct('/usr/libexec/aquadx-ctl', [ 'list-clients' ]).then(function(output) {
		return String(output || '').split(/\r?\n/).filter(function(line) {
			return line !== '';
		}).map(function(line) {
			var fields = line.split('\t');
			if (fields.length >= 3)
				return { enabled: fields[0] === '1', ip: fields[1], remark: fields.slice(2).join('\t') };
			return { enabled: true, ip: fields[0] || '', remark: fields[1] || '' };
		});
	}).catch(function() {
		return [];
	});
}

function readServerAddress() {
	return fs.exec_direct('/usr/libexec/aquadx-ctl', [ 'server-address' ]).then(function(output) {
		var fields = String(output || '').replace(/[\r\n]+$/, '').split('\t');
		return { enabled: fields[0] === '1', address: fields.slice(1).join('\t') || '' };
	}).catch(function() {
		return { enabled: false, address: '' };
	});
}

function readLog(full) {
	return fs.exec_direct('/usr/libexec/aquadx-ctl', [ full ? 'log-all' : 'log' ]).then(function(output) {
		return output || 'AquaDX 未生成日志';
	}).catch(function(err) {
		return '读取服务器运行日志失败 (' + err.message + ')';
	});
}

function readProgressLog() {
	return fs.exec_direct('/usr/libexec/aquadx-ctl', [ 'progress' ]).then(function(output) {
		return output || '';
	}).catch(function() {
		return '';
	});
}

function cleanLog(output) {
	return String(output || '').replace(/\x1b\[[0-?]*[ -\/]*[@-~]/g, '');
}

function progressText(state, output) {
	if (state.running)
		return 'ALL.Net Server 运行中';
	if (!state.starting)
		return 'ALL.Net Server 已停止';

	var lines = cleanLog(output).split(/\r?\n/).filter(function(line) { return line.trim() !== ''; });
	for (var i = lines.length - 1; i >= 0; i--) {
		var match = lines[i].match(/\[AquaDX\]\s*(.*)$/);
		if (match)
			return match[1];
	}
	return lines.length ? lines[lines.length - 1] : '正在启动，请稍候…';
}

function refreshPage() {
	return Promise.all([ readStatus(), readProgressLog(), readLog(logDetails && logDetails.open), readClients() ]).then(function(result) {
		updateStatus(result[0], result[3]);
		if (progressNode)
			progressNode.textContent = progressText(result[0], result[1]);
		if (logNode) {
			var wasAtBottom = logNode.scrollTop + logNode.clientHeight + 20 >= logNode.scrollHeight;
			logNode.textContent = cleanLog(result[2]);
			if (wasAtBottom)
				logNode.scrollTop = logNode.scrollHeight;
		}
	});
}

function statusText(state) {
	if (state.running)
		return '运行中';
	if (state.starting)
		return '正在启动';
	return '已停止';
}

function updateStatus(state, clients) {
	lastState = state;
	if (stateNode) {
		stateNode.textContent = statusText(state);
		stateNode.style.color = state.running ? '#2d8a3f' : (state.starting ? '#d47b00' : '#c0392b');
	}
	if (startButton)
		startButton.disabled = state.running || state.starting;
	if (stopButton)
		stopButton.disabled = !state.running && !state.starting;
	if (openButton)
		openButton.disabled = !state.running;
	if (!settingsDirty && autoStartCheckbox)
		autoStartCheckbox.checked = !!state.enabled;

	var nextSnapshot = JSON.stringify(clients);
	if (!settingsDirty && machineRowsNode && clientsSnapshot !== nextSnapshot)
		renderMachineRows(clients);
	if (redirectStateNode) {
		redirectStateNode.textContent = state.redirectActive ? '已启用' : '未启用';
		redirectStateNode.style.color = state.redirectActive ? '#2d8a3f' : '#777';
	}
}

function validIpv4(value) {
	var parts = value.split('.');
	return parts.length === 4 && parts.every(function(part) {
		return /^\d{1,3}$/.test(part) && Number(part) >= 0 && Number(part) <= 255;
	});
}

function validServerAddress(value) {
	if (!value || value.length > 253 || !/^[A-Za-z0-9.-]+$/.test(value))
		return false;
	if (/^[0-9.]+$/.test(value))
		return validIpv4(value);
	if (value.charAt(0) === '.' || value.charAt(value.length - 1) === '.' || value.indexOf('..') >= 0)
		return false;
	return value.split('.').every(function(label) {
		return label.length > 0 && label.length <= 63 &&
			/^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?$/.test(label);
	});
}

function markSettingsDirty() {
	settingsDirty = true;
}

function validateMachine(enabled, ip, remark) {
	if (!enabled && !ip && !remark)
		return true;
	if ((enabled || ip) && !validIpv4(ip)) {
		ui.addNotification(null, E('p', {}, '请输入有效的机台 IPv4 地址'), 'error');
		return false;
	}
	if (remark.indexOf('|') >= 0) {
		ui.addNotification(null, E('p', {}, '备注包含无效字符'), 'error');
		return false;
	}
	return true;
}

function createMachineRow(client, index) {
	var enabledCheckbox = E('input', {
		'class': 'aquadx-machine-enabled',
		'type': 'checkbox',
		'change': markSettingsDirty
	});
	enabledCheckbox.checked = client.enabled !== false;
	var ipInput = E('input', {
		'class': 'cbi-input-text aquadx-machine-ip',
		'type': 'text',
		'value': client.ip || '',
		'style': 'width:190px;',
		'input': markSettingsDirty
	});
	var remarkInput = E('input', {
		'class': 'cbi-input-text aquadx-machine-remark',
		'type': 'text',
		'placeholder': '备注',
		'value': client.remark || '',
		'style': 'width:190px;',
		'input': markSettingsDirty
	});
	var row;
	var clearButton = E('button', {
		'class': 'btn cbi-button cbi-button-reset',
		'click': function() {
			enabledCheckbox.checked = false;
			ipInput.value = '';
			remarkInput.value = '';
			markSettingsDirty();
		}
	}, '清空');
	var deleteButton = E('button', {
		'class': 'btn cbi-button cbi-button-negative',
		'style': 'margin-left:48px;',
		'click': function() {
			row.parentNode.removeChild(row);
			if (!machineRowsNode.querySelector('tr[data-machine-row="1"]'))
				machineRowsNode.insertBefore(createMachineRow({ enabled: false, ip: '', remark: '' }, 0), redirectStatusRow);
			renumberMachineRows();
			markSettingsDirty();
		}
	}, '删除');

	row = E('tr', { 'class': 'tr', 'data-machine-row': '1' }, [
		E('td', { 'class': 'td left', 'width': '35%' }, E('div', {
			'style': 'display:flex;align-items:center;gap:8px;flex-wrap:wrap;'
		}, [
			enabledCheckbox,
			E('span', { 'class': 'aquadx-machine-number' }, String(index + 1)),
			remarkInput
		])),
		E('td', { 'class': 'td left' }, E('div', {
			'style': 'display:flex;align-items:center;gap:8px;flex-wrap:wrap;'
		}, [
			E('span', {}, 'IP'), ipInput, clearButton, deleteButton
		]))
	]);
	return row;
}

function renumberMachineRows() {
	var rows = machineRowsNode.querySelectorAll('tr[data-machine-row="1"]');
	for (var i = 0; i < rows.length; i++)
		rows[i].querySelector('.aquadx-machine-number').textContent = String(i + 1);
}

function renderMachineRows(clients) {
	while (machineRowsNode.firstChild)
		machineRowsNode.removeChild(machineRowsNode.firstChild);
	var rows = clients.length ? clients : [ { enabled: false, ip: '', remark: '' } ];
	for (var i = 0; i < rows.length; i++)
		machineRowsNode.appendChild(createMachineRow(rows[i], i));
	machineRowsNode.appendChild(redirectStatusRow);
	clientsSnapshot = JSON.stringify(clients);
}

function addMachine() {
	var count = machineRowsNode.querySelectorAll('tr[data-machine-row="1"]').length;
	machineRowsNode.insertBefore(createMachineRow({ enabled: false, ip: '', remark: '' }, count), redirectStatusRow);
	markSettingsDirty();
}

function collectMachines() {
	var rows = machineRowsNode.querySelectorAll('tr[data-machine-row="1"]');
	var clients = [];
	var seen = {};
	for (var i = 0; i < rows.length; i++) {
		var enabled = rows[i].querySelector('.aquadx-machine-enabled').checked;
		var ip = String(rows[i].querySelector('.aquadx-machine-ip').value || '').trim();
		var remark = String(rows[i].querySelector('.aquadx-machine-remark').value || '').trim();
		if (!enabled && !ip && !remark)
			continue;
		if (!validateMachine(enabled, ip, remark))
			return null;
		if (seen[ip]) {
			ui.addNotification(null, E('p', {}, '机台 IP ' + ip + ' 重复'), 'error');
			return null;
		}
		seen[ip] = true;
		clients.push({ enabled: enabled, ip: ip, remark: remark });
	}
	return clients;
}

function applySettings() {
	var clients = collectMachines();
	if (clients === null)
		return Promise.resolve();
	var customAddressEnabled = customServerAddressCheckbox.checked;
	var customAddress = String(customServerAddressInput.value || '').trim();
	if (customAddressEnabled && !customAddress) {
		ui.addNotification(null, E('p', {}, '启用自定义服务器地址后必须输入地址'), 'error');
		return Promise.resolve();
	}
	if (customAddress && !validServerAddress(customAddress)) {
		ui.addNotification(null, E('p', {}, '请输入有效的服务器 IPv4 地址或主机名'), 'error');
		return Promise.resolve();
	}
	var args = [
		'apply-settings-v3',
		autoStartCheckbox.checked ? '1' : '0',
		customAddressEnabled ? '1' : '0',
		customAddress
	];
	clients.forEach(function(client) {
		args.push(client.enabled ? '1' : '0', client.ip, client.remark);
	});
	return fs.exec('/usr/libexec/aquadx-ctl', args).then(function(result) {
		if (result.code !== 0)
			throw new Error(result.stderr || result.stdout || '应用修改失败');
		settingsDirty = false;
		clientsSnapshot = '';
		ui.addNotification(null, E('p', {}, '修改已应用'), 'info');
		return refreshPage();
	}).catch(function(err) {
		ui.addNotification(null, E('p', {}, err.message), 'error');
	});
}

function setDatabaseBusy(busy) {
	databaseBusy = busy;
	if (exportButton)
		exportButton.disabled = busy;
	if (importButton)
		importButton.disabled = busy;
}

function waitDatabaseJob(remaining) {
	return fs.exec_direct('/usr/libexec/aquadx-ctl', [ 'db-job-status' ]).then(function(output) {
		var line = String(output || '').trim();
		var separator = line.indexOf('\t');
		var state = separator >= 0 ? line.substring(0, separator) : line;
		var message = separator >= 0 ? line.substring(separator + 1) : '';
		if (state === 'done')
			return message;
		if (state === 'error')
			throw new Error(message || '数据库操作失败');
		if (state !== 'running')
			throw new Error('无法读取数据库操作状态');
		if (remaining <= 0)
			throw new Error('等待数据库操作完成超时');
		return new Promise(function(resolve) {
			window.setTimeout(resolve, 1000);
		}).then(function() {
			return waitDatabaseJob(remaining - 1);
		});
	});
}

function startDatabaseJob(action) {
	return fs.exec('/usr/libexec/aquadx-ctl', [ action ]).then(function(result) {
		if (result.code !== 0)
			throw new Error(result.stderr || result.stdout || '无法启动数据库操作');
		return waitDatabaseJob(900);
	});
}

function exportDatabase() {
	if (databaseBusy)
		return;
	setDatabaseBusy(true);
	ui.addNotification(null, E('p', {}, '数据库导出中…'), 'info');
	return startDatabaseJob('export-db').then(function(downloadPath) {
		var link = document.createElement('a');
		link.href = downloadPath;
		link.download = '';
		document.body.appendChild(link);
		link.click();
		document.body.removeChild(link);
		ui.addNotification(null, E('p', {}, '数据库文件已导出'), 'info');
	}).catch(function(err) {
		ui.addNotification(null, E('p', {}, err.message), 'error');
	}).then(function() {
		setDatabaseBusy(false);
	});
}

function importDatabase() {
	if (databaseBusy)
		return;
	if (!window.confirm('导入将覆盖当前 AquaDX 数据库，系统会先自动备份现有数据库。是否继续？'))
		return;
	setDatabaseBusy(true);
	return ui.uploadFile('/tmp/aquadx-database-import.upload', null, '支持 AquaDX 导出的 .sql.gz 文件或 SQL 文件').then(function() {
		ui.addNotification(null, E('p', {}, '文件上传完成，正在导入数据库…'), 'info');
		return startDatabaseJob('import-db');
	}).then(function(backupPath) {
		ui.addNotification(null, E('p', {}, '数据库导入完成。导入前备份保存在 ' + backupPath), 'info');
	}).catch(function(err) {
		ui.addNotification(null, E('p', {}, err.message), 'error');
	}).then(function() {
		setDatabaseBusy(false);
	});
}

function runAction(action) {
	return fs.exec('/usr/libexec/aquadx-ctl', [ action ]).then(function(result) {
		if (result.code !== 0)
			throw new Error(result.stderr || result.stdout || '命令执行失败');
		ui.addNotification(null, E('p', {}, result.stdout || '操作已提交'), 'info');
		return new Promise(function(resolve) { window.setTimeout(resolve, 300); });
	}).then(refreshPage).catch(function(err) {
		ui.addNotification(null, E('p', {}, err.message), 'error');
	});
}

function openFrontend() {
	var host = window.location.hostname;
	if (host.indexOf(':') >= 0)
		host = '[' + host + ']';
	window.open('http://' + host + ':' + (lastState.port || 8088) + '/', '_blank', 'noopener');
}

return view.extend({
	load: function() {
		return Promise.all([ readStatus(), readClients(), readServerAddress() ]).then(function(result) {
			return { state: result[0], clients: result[1], serverAddress: result[2] };
		});
	},

	render: function(initialData) {
		var initialState = initialData.state;
		stateNode = E('strong');
		progressNode = E('span', {}, '正在读取启动进度…');
		logNode = E('pre', {
			'style': 'height:320px;overflow:auto;background:#111;color:#ddd;padding:12px;' +
				'border-radius:4px;white-space:pre-wrap;word-break:break-all;font:12px/1.45 monospace;'
		}, '正在读取日志…');
		logDetails = E('details', { 'style': 'margin-top:12px;' }, [
			E('summary', { 'style': 'cursor:pointer;font-weight:600;padding:8px 0;' }, '运行日志'),
			logNode
		]);
		autoStartCheckbox = E('input', {
			'type': 'checkbox',
			'change': markSettingsDirty
		});
		autoStartCheckbox.checked = !!initialState.enabled;
		customServerAddressCheckbox = E('input', {
			'type': 'checkbox',
			'change': markSettingsDirty
		});
		customServerAddressCheckbox.checked = !!initialData.serverAddress.enabled;
		customServerAddressInput = E('input', {
			'class': 'cbi-input-text',
			'type': 'text',
			'value': initialData.serverAddress.address || '',
			'spellcheck': 'false',
			'style': 'width:260px;',
			'input': markSettingsDirty
		});
		redirectStateNode = E('span', {}, '正在读取…');
		redirectStatusRow = E('tr', { 'class': 'tr' }, [
			E('td', { 'class': 'td left' }, '转发状态'),
			E('td', { 'class': 'td left' }, redirectStateNode)
		]);
		machineRowsNode = E('tbody');
		renderMachineRows(initialData.clients);

		startButton = E('button', {
			'class': 'btn cbi-button',
			'style': 'background-color:#f0ad4e;border-color:#eea236;color:#fff;',
			'click': function() { return runAction('start'); }
		}, '启动服务');
		stopButton = E('button', {
			'class': 'btn cbi-button cbi-button-negative',
			'click': function() { return runAction('stop'); }
		}, '关闭服务');
		openButton = E('button', {
			'class': 'btn cbi-button cbi-button-action',
			'click': openFrontend
		}, '打开 WebUI');
		exportButton = E('button', {
			'class': 'btn cbi-button cbi-button-neutral',
			'click': exportDatabase
		}, '导出数据库文件');
		importButton = E('button', {
			'class': 'btn cbi-button cbi-button-neutral',
			'click': importDatabase
		}, '导入数据库文件');
		var addMachineButton = E('button', {
			'class': 'btn cbi-button cbi-button-add',
			'click': addMachine
		}, '新增机台');
		var applyButton = E('button', {
			'class': 'btn cbi-button cbi-button-apply',
			'click': applySettings
		}, '应用修改');

		var page = E('div', { 'class': 'cbi-map' }, [
			E('h2', {}, 'ALL.Net Server'),
			E('div', { 'class': 'cbi-map-descr' }, '基于 AquaDX 的本地 ALL.Net 游戏服务器'),
			E('div', { 'class': 'cbi-section' }, [
				E('h3', {}, '服务状态'),
				E('table', { 'class': 'table' }, [
					E('tr', { 'class': 'tr' }, [
						E('td', { 'class': 'td left', 'width': '35%' }, '当前状态'),
						E('td', { 'class': 'td left' }, stateNode)
					]),
					E('tr', { 'class': 'tr' }, [
						E('td', { 'class': 'td left' }, '开机自动启动'),
						E('td', { 'class': 'td left' }, autoStartCheckbox)
					]),
					E('tr', { 'class': 'tr' }, [
						E('td', { 'class': 'td left' }, '启动进度'),
						E('td', { 'class': 'td left' }, progressNode)
					])
				])
			]),
			E('div', { 'class': 'cbi-section' }, [
				E('div', { 'style': 'display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;' }, [
					E('h3', { 'style': 'margin:0;' }, '机台 IP'),
					E('span', { 'style': 'color:#888;font-size:90%;' }, '机台默认访问 ALL.Net 的 TCP 80，如 80 端口被占用，可指定机台 IP 进行端口转发')
				]),
				E('table', { 'class': 'table', 'style': 'margin-top:8px;' }, machineRowsNode),
				E('div', { 'style': 'margin-top:8px;text-align:right;' }, addMachineButton)
			]),
			E('div', { 'class': 'cbi-section' }, [
				E('h3', {}, '服务器地址'),
				E('table', { 'class': 'table' }, [
					E('tr', { 'class': 'tr' }, [
						E('td', { 'class': 'td left', 'width': '35%' }, E('label', {
							'style': 'display:flex;align-items:center;gap:8px;'
						}, [ customServerAddressCheckbox, E('span', {}, '自定义服务器地址') ])),
						E('td', { 'class': 'td left' }, customServerAddressInput)
					])
				])
			]),
			logDetails,
			E('div', {
				'class': 'cbi-page-actions',
				'style': 'display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;margin-top:16px;'
			}, [
				E('div', {}, [ openButton, ' ', exportButton, ' ', importButton ]),
				E('div', { 'style': 'margin-left:auto;text-align:right;' }, [ startButton, ' ', stopButton, ' ', applyButton ])
			])
		]);

		poll.add(function() {
			return refreshPage();
		}, 2);
		updateStatus(initialState, initialData.clients);
		Promise.all([ readProgressLog(), readLog(false) ]).then(function(output) {
			progressNode.textContent = progressText(initialState, output[0]);
			logNode.textContent = cleanLog(output[1]);
			logNode.scrollTop = logNode.scrollHeight;
		});
		return page;
	},

	handleSaveApply: null,
	handleSave: null,
	handleReset: null
});
