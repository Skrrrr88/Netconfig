/**
 * NetConfig - Network Device Management Frontend
 */

class NetConfigAPI {
    constructor(baseUrl) {
        this.baseUrl = baseUrl || '';
    }

    async request(endpoint, options) {
        options = options || {};
        var url = this.baseUrl + endpoint;
        var config = Object.assign({ headers: { 'Content-Type': 'application/json' } }, options);
        if (config.body && typeof config.body === 'object') {
            config.body = JSON.stringify(config.body);
        }
        try {
            var response = await fetch(url, config);
            var data = await response.json();
            if (!response.ok) throw new Error(data.error || 'HTTP ' + response.status);
            return data;
        } catch (error) {
            console.error('API Error [' + endpoint + ']:', error);
            throw error;
        }
    }

    getDevices() { return this.request('/api/devices/'); }
    connectDevice(cfg) { return this.request('/api/devices/connect', { method: 'POST', body: cfg }); }
    disconnectDevice(ip) { return this.request('/api/devices/disconnect/' + ip, { method: 'POST' }); }
    testConnection(cfg) { return this.request('/api/devices/test', { method: 'POST', body: cfg }); }
    getRunningConfig(ip) { return this.request('/api/config/running/' + ip); }
    getStartupConfig(ip) { return this.request('/api/config/startup/' + ip); }
    pushConfig(ip, cmds) { return this.request('/api/config/push/' + ip, { method: 'POST', body: { commands: cmds } }); }
    backupConfig(ip) { return this.request('/api/config/backup/' + ip, { method: 'POST' }); }
    getGlobalVlans() { return this.request('/api/vlans/'); }
    createVlan(data) { return this.request('/api/vlans/', { method: 'POST', body: data }); }
    deleteVlan(id) { return this.request('/api/vlans/' + id, { method: 'DELETE' }); }
    deployVlan(id, targets) { return this.request('/api/vlans/' + id + '/deploy', { method: 'POST', body: { targets: targets } }); }
    getPortAssignments(ip) { return this.request('/api/vlans/ports/' + ip); }
    assignVlanToPort(ip, port, vid, mode) { return this.request('/api/vlans/ports/' + ip, { method: 'POST', body: { port: port, vlan_id: vid, mode: mode || 'access' } }); }
    getDeploymentStatus() { return this.request('/api/vlans/deployment-status'); }
    getInterfaces(ip) { return this.request('/api/devices/interfaces/' + ip); }
    deleteDevice(id) { return this.request('/api/devices/' + id, { method: 'DELETE' }); }
    reconnectDevice(ip) { return this.request('/api/devices/reconnect/' + ip, { method: 'POST' }); }
    reconnectDevice(ip) { return this.request('/api/devices/reconnect/' + ip, { method: 'POST' }); }
    checkAllStatus() { return this.request('/api/devices/status'); }
    getDescriptions(ip) { return this.request("/api/devices/descriptions/" + ip); }
    setDescription(ip, intf, desc) { return this.request("/api/devices/descriptions/" + ip, { method: "POST", body: JSON.stringify({interface: intf, description: desc}), headers: {"Content-Type": "application/json"} }); }
    getTopology() { return this.request('/api/diagram/topology'); }
    getLinks() { return this.request('/api/diagram/links'); }
}

class Toast {
    static init() {
        this.container = document.createElement('div');
        this.container.style.cssText = 'position:fixed;top:20px;right:20px;z-index:10000;display:flex;flex-direction:column;gap:8px;';
        document.body.appendChild(this.container);
    }

    static show(msg, type, duration) {
        if (!this.container) this.init();
        type = type || 'info';
        duration = duration || 4000;
        var colors = { success: '#1a3a2a', error: '#2a1a1a', warning: '#3a2a1a', info: '#1e3a5f' };
        var borders = { success: '#4ade80', error: '#ef4444', warning: '#fbbf24', info: '#60a5fa' };
        var el = document.createElement('div');
        el.style.cssText = 'background:' + colors[type] + ';border:1px solid ' + borders[type] + ';color:' + borders[type] + ';padding:12px 20px;border-radius:8px;font-size:13px;font-family:system-ui;min-width:280px;box-shadow:0 4px 12px rgba(0,0,0,.3);transition:opacity .3s;';
        el.textContent = msg;
        this.container.appendChild(el);
        setTimeout(function() { el.style.opacity = '0'; setTimeout(function() { el.remove(); }, 300); }, duration);
    }

    static success(m) { this.show(m, 'success'); }
    static error(m) { this.show(m, 'error', 6000); }
    static warning(m) { this.show(m, 'warning'); }
    static info(m) { this.show(m, 'info'); }
}

class NetConfigApp {
    constructor() {
        this.api = new NetConfigAPI();
        this.devices = [];
        this.vlans = [];
        this.selectedPorts = new Set();
        this.pollDisabled = new Set(JSON.parse(localStorage.getItem("pollDisabled") || "[]"));
    }

    init() {
        var self = this;
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', function() { self.boot(); });
        } else {
            this.boot();
        }
    }

    boot() {
        Toast.init();
        this.bindNav();
        this.bindDeviceEvents();
        this.bindConfigEvents();
        this.bindVlanEvents();
        this.bindDiagramEvents();
        this.bindSNMPEvents();
        this.loadDevices();
        this.loadVlans();
        document.querySelector('.page-devices').style.display = 'block';
        Toast.info('NetConfig ready — connect a device to get started');
        var _s = this; _s.refreshStatus(); setInterval(function(){_s.refreshStatus();}, 30000);
        setInterval(function(){ _s.tickLastSeen(); }, 1000);
        // Auto-load ports if devices exist
        setTimeout(function() { self.loadPortGrid(); }, 500);
    }

    bindNav() {
        var self = this;
        document.querySelectorAll('input[name="nav"]').forEach(function(radio) {
            radio.addEventListener('change', function() {
                document.querySelectorAll('.page').forEach(function(p) { p.style.display = 'none'; });
                document.querySelectorAll('.nav-item').forEach(function(n) { n.classList.remove('active'); });
                var id = radio.id.replace('nav-', '');
                var page = document.querySelector('.page-' + id);
                if (page) page.style.display = 'block';
                if (radio.nextElementSibling) radio.nextElementSibling.classList.add('active');
                if (id === 'diagram') self.refreshDiagram();
                if (id === 'vlans') self.loadPortGrid();
                if (id === 'snmp') { self.snmpPopulateDevices(); self.snmpLoadAlerts(); }
            });
        });
    }

    bindDeviceEvents() {
        var self = this;
        var btn = document.getElementById('btn-connect');
        if (btn) btn.addEventListener('click', function() { self.handleConnect(); });
        var testBtn = document.getElementById('btn-test-connection');
        if (testBtn) testBtn.addEventListener('click', function() { self.handleTest(); });
        var unifiBtn = document.getElementById('btn-discover-unifi');
        if (unifiBtn) unifiBtn.addEventListener('click', function() { self.handleDiscoverUnifi(); });
        var typeSelect = document.getElementById('device-type');
        if (typeSelect) typeSelect.addEventListener('change', function(e) {
            var panel = document.getElementById('unifi-settings');
            if (panel) panel.style.display = e.target.value.indexOf('unifi') === 0 ? 'block' : 'none';
        });
    }

    bindConfigEvents() {
        var self = this;
        var execBtn = document.getElementById('btn-execute-config');
        if (execBtn) execBtn.addEventListener('click', function() { self.handleExecuteConfig(); });
        var pushBtn = document.getElementById('btn-push-config');
        if (pushBtn) pushBtn.addEventListener('click', function() { self.handlePushConfig(); });
        var saveBtn = document.getElementById('btn-save-config');
        if (saveBtn) saveBtn.addEventListener('click', function() { self.handleSaveConfig(); });
        var diffBtn = document.getElementById('btn-diff-config');
        if (diffBtn) diffBtn.addEventListener('click', function() { self.handleDiffConfig(); });
        var valBtn = document.getElementById('btn-validate-config');
        if (valBtn) valBtn.addEventListener('click', function() { self.handleValidateConfig(); });
    }

    bindVlanEvents() {
        var self = this;
        var applyBtn = document.getElementById('btn-apply-vlan');
        if (applyBtn) applyBtn.addEventListener('click', function() { self.handleApplyVlan(); });
        var createBtn = document.getElementById('btn-create-vlan');
        if (createBtn) createBtn.addEventListener('click', function() { self.handleCreateVlan(); });
        var vlanDeviceSelect = document.getElementById('vlan-device-select');
        if (vlanDeviceSelect) vlanDeviceSelect.addEventListener('change', function() { self.loadPortGrid(); });
        var previewBtn = document.getElementById('btn-preview-vlan');
        if (previewBtn) previewBtn.addEventListener('click', function() { self.handlePreviewVlan(); });
        document.addEventListener('click', function(e) {
            var slot = e.target.closest('.port-slot');
            if (slot && slot.dataset.port) {
                var port = slot.dataset.port;
                if (self.selectedPorts.has(port)) { self.selectedPorts.delete(port); }
                else { self.selectedPorts.add(port); }
                slot.classList.toggle('selected');
            }
        });
    }

    bindDiagramEvents() {
        var self = this;
        var btn = document.getElementById('btn-refresh-diagram');
        if (btn) btn.addEventListener('click', function() { self.refreshDiagram(); });
    }

    getFormData() {
        return {
            hostname: (document.getElementById('device-hostname') || {}).value || '',
            ip_address: (document.getElementById('device-ip') || {}).value || '',
            device_type: (document.getElementById('device-type') || {}).value || 'cisco_ios',
            port: parseInt((document.getElementById('device-port') || {}).value || '22'),
            username: (document.getElementById('device-username') || {}).value || '',
            password: (document.getElementById('device-password') || {}).value || '',
            secret: (document.getElementById('device-secret') || {}).value || '',
            unifi_controller_url: (document.getElementById('unifi-url') || {}).value || '',
            unifi_site: (document.getElementById('unifi-site') || {}).value || 'default'
        };
    }

    async handleConnect() {
        var data = this.getFormData();
        if (!data.ip_address) data.ip_address = data.hostname;
        if (!data.ip_address) { Toast.warning('Enter an IP address or hostname'); return; }
        Toast.info('Connecting to ' + (data.hostname || data.ip_address) + '...');
        try {
            var result = await this.api.connectDevice(data);
            if (result.success) { Toast.success('Connected to ' + (data.hostname || data.ip_address)); await this.loadDevices(); }
            else Toast.error(result.error || 'Connection failed');
        } catch (e) { Toast.error('Connection failed: ' + e.message); }
    }

    async handleTest() {
        var data = this.getFormData();
        if (!data.ip_address) data.ip_address = data.hostname;
        if (!data.ip_address) { Toast.warning('Enter an IP address'); return; }
        Toast.info('Testing connection...');
        try {
            var result = await this.api.testConnection(data);
            if (result.success) Toast.success('Test passed! Prompt: ' + result.prompt);
            else Toast.error(result.error || 'Test failed');
        } catch (e) { Toast.error(e.message); }
    }

    async handleDiscoverUnifi() {
        var data = this.getFormData();
        if (!data.unifi_controller_url) { Toast.warning('Enter UniFi Controller URL'); return; }
        Toast.info('Discovering UniFi devices...');
        try {
            var result = await this.api.connectDevice(Object.assign({}, data, { device_type: 'unifi_switch' }));
            if (result.success && result.devices) {
                Toast.success('Found ' + result.devices.length + ' device(s)');
                await this.loadDevices();
            } else Toast.error(result.error || 'Discovery failed');
        } catch (e) { Toast.error(e.message); }
    }

    async loadDevices() {
        try {
            this.devices = await this.api.getDevices();
            this.renderDeviceTable();
            this.populateDeviceSelects();
        } catch (e) { /* silent on first load */ }
    }

    async loadVlans() {
        try {
            this.vlans = await this.api.getGlobalVlans();
            this.renderVlanGrid();
            this.populateVlanSelects();
        } catch (e) { /* silent */ }
    }

    renderDeviceTable() {
        var tbody = document.getElementById('device-table-body');
        if (!tbody) return;
        if (!this.devices.length) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#666;">No devices connected.</td></tr>';
            return;
        }
        var html = '';
        for (var i = 0; i < this.devices.length; i++) {
            var d = this.devices[i];
            var isUnifi = d.device_type && d.device_type.indexOf('unifi') === 0;
            html += '<tr>';
            html += '<td><span id="sd-' + d.ip_address + '" class="status-dot ' + (d.is_online ? 'status-online' : 'status-offline') + '"></span>' + (d.is_online ? 'Online' : 'Offline') + '</td>';
            html += '<td style="font-weight:500;' + (isUnifi ? 'color:#60a5fa;' : '') + '">' + d.hostname + '</td>';
            html += '<td style="font-family:monospace;">' + d.ip_address + '</td>';
            html += '<td>' + (d.device_type || '—') + '</td>';
            html += '<td>' + (d.platform || '—') + '</td>';
            html += '<td>' + (d.uptime || '—') + '</td>';
            html += '<td><span id="ls-' + d.ip_address + '" data-time="' + (d.last_seen || '') + '">' + this.timeAgo(d.last_seen) + '</span></td>';
            html += '<td><button class="btn btn-secondary" style="padding:4px 10px;font-size:11px;" onclick="app.handleDisconnect(\'' + d.ip_address + '\')">Disconnect</button> ';
            html += '<button class="btn btn-primary" style="padding:4px 10px;font-size:11px;margin-left:4px;" onclick="app.handleReconnect(\'' + d.ip_address + '\')">Reconnect</button> ';
            var pollState = this.pollDisabled.has(d.ip_address) ? 'OFF' : 'ON';
            var pollColor = pollState === 'ON' ? '#4ade80' : '#ef4444';
            html += '<button class="btn btn-secondary" style="padding:4px 10px;font-size:11px;margin-left:4px;border:1px solid ' + pollColor + ';color:' + pollColor + ';" onclick="app.togglePoll(\'' + d.ip_address + '\')">Poll: ' + pollState + '</button> ';
            html += '<button class="btn btn-danger" style="padding:4px 10px;font-size:11px;margin-left:4px;" onclick="app.handleDeleteDevice(' + d.id + ')">Delete</button></td>';
            html += '</tr>';
        }
        tbody.innerHTML = html;
    }

    editDescription(ip, intf, currentDesc) {
        var newDesc = prompt("Description for " + intf + ":", currentDesc || "");
        if (newDesc === null) return;
        var self = this;
        this.api.setDescription(ip, intf, newDesc).then(function(r) {
            if (r.success) { Toast.success("Description updated"); self.loadPortGrid(); }
            else { Toast.error(r.error || "Failed"); }
        });
    }

    togglePoll(ip) {
        if (this.pollDisabled.has(ip)) {
            this.pollDisabled.delete(ip);
            Toast.success("Polling enabled for " + ip);
        } else {
            this.pollDisabled.add(ip);
            Toast.info("Polling disabled for " + ip);
        }
        localStorage.setItem("pollDisabled", JSON.stringify([...this.pollDisabled]));
        this.renderDeviceTable();
    }

    async handleDisconnect(ip) {
        try {
            await this.api.disconnectDevice(ip);
            Toast.success('Disconnected from ' + ip);
            await this.loadDevices();
        } catch (e) { Toast.error(e.message); }
    }

    timeAgo(iso) {
        if (!iso || iso === 'None' || iso === 'null') return 'Never';
        var then;
        if (iso.indexOf('T') > -1) {
            then = new Date(iso.indexOf('Z') === -1 && iso.indexOf('+') === -1 ? iso + 'Z' : iso);
        } else {
            then = new Date(iso);
        }
        if (isNaN(then.getTime())) return 'Never';
        var s = Math.floor((new Date() - then) / 1000);
        if (s < 0) s = 0;
        var d = Math.floor(s / 86400);
        var h = Math.floor((s % 86400) / 3600);
        var m = Math.floor((s % 3600) / 60);
        var sec = s % 60;
        if (d > 0) return d + 'd ' + h + 'h ' + m + 'm ago';
        if (h > 0) return h + 'h ' + m + 'm ' + sec + 's ago';
        if (m > 0) return m + 'm ' + sec + 's ago';
        return sec + 's ago';
    }

    async refreshStatus() {
        try {
            var st = await this.api.checkAllStatus();
            if (!st) return;
            for (var i = 0; i < st.length; i++) {
                var s = st[i];
                if (this.pollDisabled && this.pollDisabled.has(s.ip_address)) continue;
                var dot = document.getElementById('sd-' + s.ip_address);
                if (dot) dot.style.background = s.is_online ? '#4ade80' : '#ef4444';
                var ls = document.getElementById('ls-' + s.ip_address);
                if (ls) { ls.setAttribute('data-time', s.last_seen || ''); ls.textContent = this.timeAgo(s.last_seen); }
            }
        } catch (e) {}
    }

    async handleReconnect(ip) {
        try {
            Toast.info('Reconnecting to ' + ip + '...');
            var result = await this.api.reconnectDevice(ip);
            if (result.success) {
                Toast.success(result.message || 'Reconnected!');
                await this.loadDevices();
            } else {
                Toast.error(result.error || 'Reconnect failed');
            }
        } catch (e) { Toast.error(e.message); }
    }


    async handleDeleteDevice(id) {
        if (!confirm('Delete this device permanently?')) return;
        try {
            var result = await this.api.deleteDevice(id);
            if (result.success) { Toast.success(result.message || 'Device deleted'); await this.loadDevices(); }
            else Toast.error(result.error || 'Delete failed');
        } catch (e) { Toast.error(e.message); }
    }

    async handleDeleteVlan(vlanId) {
        if (!confirm('Delete VLAN ' + vlanId + '? This will NOT remove it from devices.')) return;
        try {
            var result = await this.api.deleteVlan(vlanId);
            if (result.success) { Toast.success(result.message || 'VLAN deleted'); await this.loadVlans(); }
            else Toast.error(result.error || 'Delete failed');
        } catch (e) { Toast.error(e.message); }
    }

    populateDeviceSelects() {
        var options = '';
        for (var i = 0; i < this.devices.length; i++) {
            var d = this.devices[i];
            options += '<option value="' + d.ip_address + '">' + d.hostname + ' (' + d.ip_address + ')</option>';
        }
        if (!options) options = '<option>No devices</option>';
        
        var selects = ['config-device-select', 'vlan-device-select'];
        for (var j = 0; j < selects.length; j++) {
            var el = document.getElementById(selects[j]);
            if (el) el.innerHTML = options;
        }
        // Auto-load port grid if VLANs page is visible
        var vlansPage = document.querySelector('.page-vlans');
        if (vlansPage && vlansPage.style.display !== 'none') {
            this.loadPortGrid();
        }
    }

    populateVlanSelects() {
        var options = '';
        for (var i = 0; i < this.vlans.length; i++) {
            var v = this.vlans[i];
            options += '<option value="' + v.vlan_id + '">VLAN ' + v.vlan_id + ' — ' + v.name + '</option>';
        }
        document.querySelectorAll('.vlan-select-dropdown').forEach(function(el) { el.innerHTML = options; });
    }

    renderVlanGrid() {
        var container = document.getElementById('vlan-grid');
        if (!container) return;
        var html = '';
        for (var i = 0; i < this.vlans.length; i++) {
            var v = this.vlans[i];
            html += '<div class="vlan-card">';
            html += '<div class="vlan-id" style="color:' + this.vlanColor(v.vlan_id) + ';">' + v.vlan_id + '</div>';
            html += '<div class="vlan-name">' + v.name + '</div>';
            html += '<div class="vlan-subnet">' + (v.subnet || 'No subnet') + '</div>';
            html += '<div class="vlan-ports">Gateway: ' + (v.gateway || 'N/A') + '</div>';
            html += '<button class="btn btn-danger" style="padding:4px 8px;font-size:10px;margin-top:8px;" onclick="app.handleDeleteVlan(' + v.vlan_id + ')">Delete</button>';
            html += '</div>';
        }
        container.innerHTML = html;
    }

    vlanColor(id) {
        var colors = { 1: '#888', 10: '#60a5fa', 20: '#4ade80', 30: '#fbbf24', 40: '#c084fc', 50: '#67e8f9', 99: '#f87171' };
        return colors[id] || '#888';
    }

    async handleExecuteConfig() {
        var ip = (document.getElementById('config-device-select') || {}).value;
        var action = (document.getElementById('config-action-select') || {}).value;
        if (!ip) { Toast.warning('Select a device'); return; }
        Toast.info('Executing: ' + action + '...');
        try {
            var result;
            if (action === 'Pull Running Config') result = await this.api.getRunningConfig(ip);
            else if (action === 'Pull Startup Config') result = await this.api.getStartupConfig(ip);
            else if (action === 'Backup Config') result = await this.api.backupConfig(ip);
            else { Toast.warning('Select an action'); return; }
            if (result.config) {
                document.getElementById('config-output').textContent = result.config;
                Toast.success('Config retrieved');
            } else if (result.success) Toast.success(result.message || 'Done');
            else Toast.error(result.error || 'Failed');
        } catch (e) { Toast.error(e.message); }
    }

    async handlePushConfig() {
        var ip = (document.getElementById('config-device-select') || {}).value;
        var cmds = (document.getElementById('config-push-input') || {}).value;
        if (!ip) { Toast.warning('Select a device'); return; }
        if (!cmds || !cmds.trim()) { Toast.warning('Enter commands'); return; }
        if (!confirm('⚠️ Push configuration to ' + ip + '?')) return;
        var cmdList = cmds.split('\n').filter(function(c) { return c.trim(); });
        try {
            var result = await this.api.pushConfig(ip, cmdList);
            if (result.success) {
                Toast.success('Config pushed successfully');
                document.getElementById('config-output').textContent = result.output || 'Done';
            } else Toast.error(result.error || 'Push failed');
        } catch (e) { Toast.error(e.message); }
    }

    handleSaveConfig() {
        var output = (document.getElementById('config-output') || {}).textContent;
        if (!output || output === 'No configuration loaded.') { Toast.warning('No config to save'); return; }
        var blob = new Blob([output], { type: 'text/plain' });
        var a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'config_' + new Date().toISOString().replace(/[:.]/g, '-') + '.txt';
        a.click();
        Toast.success('Saved to file');
    }

    async handleDiffConfig() {
        var ip = (document.getElementById('config-device-select') || {}).value;
        if (!ip) { Toast.warning('Select a device'); return; }
        Toast.info('Generating diff...');
        try {
            var run = await this.api.getRunningConfig(ip);
            var start = await this.api.getStartupConfig(ip);
            if (run.config && start.config) {
                var diff = this.computeDiff(start.config, run.config);
                document.getElementById('config-output').innerHTML = diff;
                Toast.success('Diff generated');
            }
        } catch (e) { Toast.error(e.message); }
    }

    handleValidateConfig() {
        var cmds = (document.getElementById('config-push-input') || {}).value;
        if (!cmds || !cmds.trim()) { Toast.warning('No commands to validate'); return; }
        var errors = [];
        var lines = cmds.split('\n');
        for (var i = 0; i < lines.length; i++) {
            var t = lines[i].trim();
            if (!t || t.charAt(0) === '!') continue;
            if (t.indexOf('interface') === 0 && !t.match(/interface\s+\S+/)) errors.push('Line ' + (i + 1) + ': Invalid interface');
            if (t.match(/^\d/)) errors.push('Line ' + (i + 1) + ': Should not start with number');
        }
        if (errors.length === 0) Toast.success('Validation passed ✓');
        else Toast.error(errors.length + ' error(s): ' + errors[0]);
    }

    computeDiff(oldText, newText) {
        var oldLines = oldText.split('\n');
        var newLines = newText.split('\n');
        var result = [];
        var max = Math.max(oldLines.length, newLines.length);
        for (var i = 0; i < max; i++) {
            var o = oldLines[i] || '';
            var n = newLines[i] || '';
            if (o === n) result.push('  ' + n);
            else {
                if (o) result.push('<span style="color:#ef4444;">- ' + o + '</span>');
                if (n) result.push('<span style="color:#4ade80;">+ ' + n + '</span>');
            }
        }
        return result.join('\n');
    }

    async loadPortGrid() {
        var container = document.getElementById('port-grid');
        if (!container) return;
        var ip = (document.getElementById('vlan-device-select') || {}).value;
        // If dropdown is empty or invalid, try to get first online device
        if (!ip || ip === 'No devices' || ip === '') {
            try {
                var devs = await this.api.getDevices();
                if (devs && devs.length > 0) {
                    var onlineDev = devs.find(function(d) { return d.is_online; }) || devs[0];
                    ip = onlineDev.ip_address;
                    // Also populate the dropdown
                    var sel = document.getElementById('vlan-device-select');
                    if (sel) {
                        var opts = '';
                        for (var i = 0; i < devs.length; i++) {
                            opts += '<option value="' + devs[i].ip_address + '">' + devs[i].hostname + ' (' + devs[i].ip_address + ')</option>';
                        }
                        sel.innerHTML = opts;
                    }
                } else {
                    container.innerHTML = '<div style="color:#888;padding:12px;">Connect a device first</div>';
                    return;
                }
            } catch(e) {
                container.innerHTML = '<div style="color:#888;padding:12px;">Connect a device first</div>';
                return;
            }
        }
        if (!ip || !container || ip === 'No devices') { if (container) container.innerHTML = '<div style="color:#888;padding:12px;">Connect a device first</div>'; return; }
        container.innerHTML = '<div style="color:#888;padding:12px;">Loading ports...</div>';
        try {
            var result = await this.api.getInterfaces(ip);
            if (result.success && result.interfaces) {
                var html = '<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr style="border-bottom:1px solid #444;"><th style="padding:6px;text-align:left;">Port</th><th style="padding:6px;text-align:left;">Status</th><th style="padding:6px;text-align:left;">VLAN</th><th style="padding:6px;text-align:left;">Speed</th><th style="padding:6px;text-align:left;">Description</th><th style="padding:6px;">Edit</th></tr></thead><tbody>';
                for (var i = 0; i < result.interfaces.length; i++) {
                    var iface = result.interfaces[i];
                    var statusColor = iface.status === 'up' ? '#4ade80' : '#ef4444';
                    var desc = iface.description || '';
                    html += '<tr class="port-slot" data-port="' + iface.port + '" style="border-bottom:1px solid #333;cursor:pointer;">';
                    html += '<td style="padding:6px;font-weight:500;">' + iface.port + '</td>';
                    html += '<td style="padding:6px;color:' + statusColor + ';">' + (iface.status || '—') + '</td>';
                    html += '<td style="padding:6px;">' + (iface.vlan || '—') + '</td>';
                    html += '<td style="padding:6px;">' + (iface.speed || '—') + '</td>';
                    html += '<td style="padding:6px;color:#aaa;">' + (desc || '<em>none</em>') + '</td>';
                    html += '<td style="padding:6px;text-align:center;">';
                    html += '<button class="btn-edit-desc" data-ip="' + ip + '" data-port="' + iface.port + '" data-desc="' + desc + '" style="background:#3b82f6;border:none;color:#fff;padding:2px 8px;border-radius:3px;cursor:pointer;font-size:11px;">Edit</button>';
                    html += '</td>';
                    html += '<td style="padding:6px;text-align:center;">';
                    html += '</td>';
                    html += '</tr>';
                }
                html += '</tbody></table>';
                container.innerHTML = html || '<div style="color:#888;padding:12px;">No interfaces found</div>';
                this.selectedPorts.clear();
                this.loadAssignments();
                document.querySelectorAll('.btn-edit-desc').forEach(function(btn) {
                    btn.addEventListener('click', function(e) {
                        e.stopPropagation();
                        app.editDescription(btn.dataset.ip, btn.dataset.port, btn.dataset.desc);
                    });
                });
            } else {
                container.innerHTML = '<div style="color:#ef4444;padding:12px;">' + (result.error || 'Failed to load ports') + '</div>';
            }
        } catch (e) {
            container.innerHTML = '<div style="color:#ef4444;padding:12px;">Error: ' + e.message + '</div>';
        }
    }

    async loadAssignments() {
        var ip = (document.getElementById('vlan-device-select') || {}).value;
        var tbody = document.getElementById('vlan-assignment-tbody');
        if (!ip || !tbody) return;
        try {
            var assignments = await this.api.getPortAssignments(ip);
            if (!assignments || !assignments.length) {
                tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#666;">No assignments found</td></tr>';
                return;
            }
            var html = '';
            for (var i = 0; i < assignments.length; i++) {
                var a = assignments[i];
                var statusColor = a.status === 'up' ? '#4ade80' : '#ef4444';
                html += '<tr>';
                html += '<td style="font-family:monospace;">' + a.port + '</td>';
                html += '<td><span style="font-weight:600;">' + (a.vlan || '—') + '</span></td>';
                html += '<td>' + (a.mode || 'access') + '</td>';
                html += '<td>' + (a.description || '—') + '</td>';
                html += '<td><span style="color:' + statusColor + ';">' + (a.status || '—') + '</span></td>';
                html += '<td><button class="btn btn-secondary" style="padding:2px 8px;font-size:10px;" onclick="app.handleEditPort(\'' + a.port + '\',\'' + ip + '\')">Edit</button></td>';
                html += '</tr>';
            }
            tbody.innerHTML = html;
        } catch (e) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#ef4444;">Error: ' + e.message + '</td></tr>';
        }
    }

    async handleEditPort(port, ip) {
        var vlanId = prompt('Enter VLAN ID for ' + port + ':');
        if (!vlanId) return;
        var mode = confirm('Trunk mode? (OK=Trunk, Cancel=Access)') ? 'trunk' : 'access';
        try {
            var result = await this.api.assignVlanToPort(ip, port, parseInt(vlanId), mode);
            if (result.success) {
                Toast.success('VLAN ' + vlanId + ' assigned to ' + port);
                await this.loadAssignments();
                await this.loadPortGrid();
            } else {
                Toast.error(result.error || 'Failed');
            }
        } catch (e) { Toast.error(e.message); }
    }

    async handleApplyVlan() {
        var ports = Array.from(this.selectedPorts);
        var vlanSelect = document.getElementById('vlan-assign-select');
        var ip = (document.getElementById('vlan-device-select') || {}).value;
        if (!ports.length) { Toast.warning('Select ports first'); return; }
        if (!vlanSelect || !vlanSelect.value) { Toast.warning('Select a VLAN'); return; }
        var vlanId = parseInt(vlanSelect.value);
        Toast.info('Assigning VLAN ' + vlanId + ' to ' + ports.length + ' port(s)...');
        try {
            var results = await Promise.all(ports.map(function(p) { return this.api.assignVlanToPort(ip, p, vlanId); }.bind(this)));
            var ok = results.filter(function(r) { return r.success; }).length;
            if (ok) Toast.success('VLAN assigned to ' + ok + ' port(s)');
            this.selectedPorts.clear();
            document.querySelectorAll('.port-slot.selected').forEach(function(el) { el.classList.remove('selected'); });
        } catch (e) { Toast.error(e.message); }
    }

    async handleCreateVlan() {
        var data = {
            vlan_id: parseInt((document.getElementById('new-vlan-id') || {}).value),
            name: (document.getElementById('new-vlan-name') || {}).value || '',
            subnet: (document.getElementById('new-vlan-subnet') || {}).value || '',
            gateway: (document.getElementById('new-vlan-gateway') || {}).value || '',
            description: (document.getElementById('new-vlan-description') || {}).value || '',
            deploy_to: (document.getElementById('new-vlan-deploy') || {}).value || 'all'
        };
        if (!data.vlan_id || !data.name) { Toast.warning('VLAN ID and Name required'); return; }
        if (data.vlan_id < 1 || data.vlan_id > 4094) { Toast.error('VLAN ID must be 1-4094'); return; }
        Toast.info('Creating VLAN ' + data.vlan_id + '...');
        try {
            var result = await this.api.createVlan(data);
            if (result.success) { Toast.success('VLAN ' + data.vlan_id + ' created & deployed'); await this.loadVlans(); }
            else Toast.error(result.error || 'Failed');
        } catch (e) { Toast.error(e.message); }
    }

    handlePreviewVlan() {
        var id = (document.getElementById('new-vlan-id') || {}).value;
        var name = (document.getElementById('new-vlan-name') || {}).value;
        if (!id || !name) { Toast.warning('Fill in VLAN ID and Name'); return; }
        var target = (document.getElementById('new-vlan-deploy') || {}).value || 'all';
        alert('Preview:\n\nvlan ' + id + '\n  name ' + name + '\n\nDeploy to: ' + target);
    }

    async refreshDiagram() {
        var self = this;
        try {
            var topology = await this.api.getTopology();
            this.renderTopology(topology.nodes || []);
        } catch (e) {
            this.renderTopology(this.devices.map(function(d) {
                return {
                    id: d.ip_address, hostname: d.hostname, ip: d.ip_address,
                    isOnline: d.is_online, isUnifi: d.device_type && d.device_type.indexOf('unifi') === 0,
                    type: (d.device_type && d.device_type.indexOf('gateway') >= 0) ? 'gateway' : 'switch'
                };
            }));
        }
    }

    renderTopology(nodes) {
        var svg = document.getElementById('topology-svg');
        if (!svg || !nodes.length) return;
        var ns = 'http://www.w3.org/2000/svg';
        svg.innerHTML = '';

        var bg = document.createElementNS(ns, 'rect');
        bg.setAttribute('width', '900');
        bg.setAttribute('height', '580');
        bg.setAttribute('fill', '#0a0c10');
        svg.appendChild(bg);

        var layers = { gateway: [], router: [], core_switch: [], switch: [], ap: [] };
        for (var i = 0; i < nodes.length; i++) {
            var n = nodes[i];
            var layer = layers[n.type] || layers['switch'];
            layer.push(n);
        }

        var y = 80;
        var layerKeys = ['gateway', 'router', 'core_switch', 'switch', 'ap'];
        for (var k = 0; k < layerKeys.length; k++) {
            var layer = layers[layerKeys[k]];
            if (!layer.length) continue;
            var spacing = 900 / (layer.length + 1);
            for (var j = 0; j < layer.length; j++) {
                layer[j].x = spacing * (j + 1);
                layer[j].y = y;
            }
            y += 130;
        }

        var allNodes = [];
        for (var k = 0; k < layerKeys.length; k++) {
            allNodes = allNodes.concat(layers[layerKeys[k]]);
        }

        for (var i = 0; i < allNodes.length; i++) {
            for (var j = i + 1; j < allNodes.length; j++) {
                var a = allNodes[i], b = allNodes[j];
                var la = layerKeys.indexOf(a.type), lb = layerKeys.indexOf(b.type);
                if (la < 0) la = 3;
                if (lb < 0) lb = 3;
                if (Math.abs(la - lb) === 1) {
                    var line = document.createElementNS(ns, 'line');
                    line.setAttribute('x1', a.x);
                    line.setAttribute('y1', a.y + 25);
                    line.setAttribute('x2', b.x);
                    line.setAttribute('y2', b.y - 25);
                    var online = a.isOnline && b.isOnline;
                    line.setAttribute('stroke', online ? '#4ade80' : '#ef4444');
                    line.setAttribute('stroke-width', '1.5');
                    if (!online) line.setAttribute('stroke-dasharray', '4,4');
                    svg.appendChild(line);
                }
            }
        }

        for (var i = 0; i < allNodes.length; i++) {
            var node = allNodes[i];
            var g = document.createElementNS(ns, 'g');
            g.style.cursor = 'pointer';

            var rect = document.createElementNS(ns, 'rect');
            rect.setAttribute('x', node.x - 55);
            rect.setAttribute('y', node.y - 25);
            rect.setAttribute('width', '110');
            rect.setAttribute('height', '50');
            rect.setAttribute('rx', '8');
            rect.setAttribute('fill', '#161922');
            var strokeColor = node.isOnline ? (node.isUnifi ? '#60a5fa' : '#4ade80') : '#ef4444';
            rect.setAttribute('stroke', strokeColor);
            rect.setAttribute('stroke-width', '1.5');
            g.appendChild(rect);

            var text = document.createElementNS(ns, 'text');
            text.setAttribute('x', node.x);
            text.setAttribute('y', node.y - 2);
            text.setAttribute('text-anchor', 'middle');
            text.setAttribute('fill', '#fff');
            text.setAttribute('font-size', '10');
            text.setAttribute('font-weight', '600');
            text.setAttribute('font-family', 'system-ui');
            text.textContent = (node.hostname || '').substring(0, 14);
            g.appendChild(text);

            var ip = document.createElementNS(ns, 'text');
            ip.setAttribute('x', node.x);
            ip.setAttribute('y', node.y + 12);
            ip.setAttribute('text-anchor', 'middle');
            ip.setAttribute('fill', '#888');
            ip.setAttribute('font-size', '9');
            ip.setAttribute('font-family', 'monospace');
            ip.textContent = node.ip || '';
            g.appendChild(ip);

            svg.appendChild(g);
        }
    }
     // ===== SNMP MODULE =====

    bindSNMPEvents() {
        var self = this;
        var pollBtn = document.getElementById('btn-snmp-poll');
        if (pollBtn) pollBtn.addEventListener('click', function() { self.snmpPoll(); });

        var clearBtn = document.getElementById('btn-clear-alerts');
        if (clearBtn) clearBtn.addEventListener('click', function() { self.snmpClearAlerts(); });

        var autoCheck = document.getElementById('snmp-auto-poll');
        if (autoCheck) autoCheck.addEventListener('change', function() {
            if (autoCheck.checked) {
                self._snmpInterval = setInterval(function() { self.snmpPoll(); }, 30000);
                Toast.info('SNMP auto-poll enabled (30s)');
            } else {
                clearInterval(self._snmpInterval);
                Toast.info('SNMP auto-poll disabled');
            }
        });
    }

    async snmpPopulateDevices() {
        var sel = document.getElementById('snmp-device-select');
        if (!sel) return;
        try {
            var devs = await this.api.getDevices();
            var html = '';
            for (var i = 0; i < devs.length; i++) {
                html += '<option value="' + devs[i].ip_address + '">' + devs[i].hostname + ' (' + devs[i].ip_address + ')</option>';
            }
            sel.innerHTML = html || '<option>No devices</option>';
        } catch(e) {}
    }

    async snmpPoll() {
        var sel = document.getElementById('snmp-device-select');
        if (!sel || !sel.value) { Toast.error('Select a device'); return; }
        var ip = sel.value;
        Toast.info('Polling ' + ip + '...');

        try {
            var r = await this.api.request('/api/snmp/poll/' + ip);
            if (!r.success) { Toast.error(r.error || 'Poll failed'); return; }

            // CPU
            var cpu = r.cpu;
            var cpuEl = document.getElementById('snmp-cpu');
            var cpuBar = document.getElementById('snmp-cpu-bar');
            if (cpuEl) cpuEl.textContent = cpu !== null ? cpu + '%' : '—';
            if (cpuBar && cpu !== null) {
                cpuBar.style.width = cpu + '%';
                cpuBar.style.background = cpu > 80 ? '#ef4444' : cpu > 60 ? '#facc15' : '#4ade80';
            }

            // Memory
            var mem = r.memory;
            var memEl = document.getElementById('snmp-mem');
            var memBar = document.getElementById('snmp-mem-bar');
            if (memEl) memEl.textContent = mem !== null ? mem + '%' : '—';
            if (memBar && mem !== null) {
                memBar.style.width = mem + '%';
                memBar.style.background = mem > 85 ? '#ef4444' : mem > 70 ? '#facc15' : '#4ade80';
            }

            // Temperature
            var temp = r.temperature;
            var tempEl = document.getElementById('snmp-temp');
            var tempBar = document.getElementById('snmp-temp-bar');
            if (tempEl) tempEl.textContent = temp !== null ? temp + '°F' : '—';
            if (tempBar && temp !== null) {
                var pct = Math.min(100, (temp / 80) * 100);
                tempBar.style.width = pct + '%';
                tempBar.style.background = temp > 149 ? '#ef4444' : temp > 131 ? '#facc15' : '#4ade80';
            }

            // Uptime
            var upEl = document.getElementById('snmp-uptime');
            if (upEl) {
                var ut = r.system.sysUptime || '';
                if (ut && ut.match(/^\d+$/)) {
                    var secs = Math.floor(parseInt(ut) / 100);
                    var d = Math.floor(secs / 86400);
                    var h = Math.floor((secs % 86400) / 3600);
                    var m = Math.floor((secs % 3600) / 60);
                    upEl.textContent = d + 'd ' + h + 'h ' + m + 'm';
                } else {
                    upEl.textContent = ut || '—';
                }
            }

            // Interfaces
            this.snmpRenderInterfaces(r.interfaces || []);

            // System Info
            this.snmpRenderSysInfo(r.system || {});

            // Environment
            this.snmpRenderEnvironment(r.environment || {}, temp);

            // Alerts
            this.snmpLoadAlerts();

            // Last poll
            var lp = document.getElementById('snmp-last-poll');
            if (lp) lp.textContent = 'Last poll: ' + new Date().toLocaleTimeString();

            Toast.success('SNMP poll complete');
        } catch(e) {
            Toast.error('Poll error: ' + e.message);
        }
    }

    snmpRenderInterfaces(interfaces) {
        var tbody = document.getElementById('snmp-interfaces-body');
        if (!tbody) return;
        if (!interfaces.length) { tbody.innerHTML = '<tr><td colspan="6" style="padding:12px;color:#666;">No interface data</td></tr>'; return; }

        var html = '';
        for (var i = 0; i < interfaces.length; i++) {
            var iface = interfaces[i];
            var statusColor = iface.status === 'up' ? '#4ade80' : '#ef4444';
            var errColor = iface.errors > 0 ? '#facc15' : '#94a3b8';
            html += '<tr style="border-bottom:1px solid #1e293b;">';
            html += '<td style="padding:6px;">' + iface.interface + '</td>';
            html += '<td style="padding:6px;text-align:right;color:#60a5fa;">' + iface.in_mbps.toFixed(2) + '</td>';
            html += '<td style="padding:6px;text-align:right;color:#a78bfa;">' + iface.out_mbps.toFixed(2) + '</td>';
            html += '<td style="padding:6px;text-align:right;color:' + errColor + ';">' + iface.errors + '</td>';
            html += '<td style="padding:6px;text-align:right;color:#94a3b8;">' + (iface.speed || '—') + '</td>';
            html += '<td style="padding:6px;text-align:center;"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:' + statusColor + ';"></span> ' + iface.status + '</td>';
            html += '</tr>';
        }
        tbody.innerHTML = html;
    }

    snmpRenderSysInfo(sys) {
        var el = document.getElementById('snmp-sysinfo');
        if (!el) return;
        var html = '<table style="width:100%;font-size:12px;">';
        var fields = [
            ['sysName', sys.sysName],
            ['sysDescr', sys.sysDescr],
            ['sysLocation', sys.sysLocation],
            ['sysContact', sys.sysContact],
            ['Serial', sys.serial],
            ['Firmware', sys.firmware],
        ];
        for (var i = 0; i < fields.length; i++) {
            html += '<tr><td style="padding:4px 8px;color:#94a3b8;white-space:nowrap;">' + fields[i][0] + '</td>';
            html += '<td style="padding:4px 8px;color:#f1f5f9;word-break:break-all;">' + (fields[i][1] || '—') + '</td></tr>';
        }
        html += '</table>';
        el.innerHTML = html;
    }

    snmpRenderEnvironment(env, temp) {
        var el = document.getElementById('snmp-environment');
        if (!el) return;
        var html = '';

        var psus = env.psus || [];
        for (var i = 0; i < psus.length; i++) {
            var color = psus[i].status === 'OK' ? '#4ade80' : '#ef4444';
            html += '<div style="padding:4px 0;"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:' + color + ';margin-right:8px;"></span>PSU ' + psus[i].id + ': ' + psus[i].status + '</div>';
        }

        var fans = env.fans || [];
        for (var i = 0; i < fans.length; i++) {
            var color = fans[i].status === 'OK' ? '#4ade80' : '#ef4444';
            html += '<div style="padding:4px 0;"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:' + color + ';margin-right:8px;"></span>Fan ' + fans[i].id + ': ' + fans[i].status + '</div>';
        }

        if (temp !== null) {
            var tColor = temp > 149 ? '#ef4444' : temp > 131 ? '#facc15' : '#4ade80';
            html += '<div style="padding:4px 0;margin-top:8px;"><span style="color:' + tColor + ';font-weight:600;">' + temp + '°F</span> <span style="color:#94a3b8;">/ ' + Math.round(temp * 9/5 + 32) + '°F</span></div>';
        }

        el.innerHTML = html || '<div style="color:#666;">No environment data available</div>';
    }

    async snmpLoadAlerts() {
        var tbody = document.getElementById('snmp-alerts-body');
        if (!tbody) return;
        try {
            var r = await this.api.request('/api/snmp/alerts');
            if (!r.success || !r.alerts.length) {
                tbody.innerHTML = '<tr><td colspan="4" style="padding:12px;color:#666;">No alerts</td></tr>';
                return;
            }
            var html = '';
            var colors = {critical: '#ef4444', warning: '#facc15', info: '#4ade80'};
            var labels = {critical: '● CRIT', warning: '● WARN', info: '● INFO'};
            for (var i = 0; i < r.alerts.length; i++) {
                var a = r.alerts[i];
                var c = colors[a.severity] || '#94a3b8';
                html += '<tr style="border-bottom:1px solid #1e293b;">';
                html += '<td style="padding:4px 6px;color:#94a3b8;">' + a.time + '</td>';
                html += '<td style="padding:4px 6px;color:' + c + ';font-weight:600;">' + (labels[a.severity] || a.severity) + '</td>';
                html += '<td style="padding:4px 6px;">' + a.source + '</td>';
                html += '<td style="padding:4px 6px;">' + a.message + '</td>';
                html += '</tr>';
            }
            tbody.innerHTML = html;
        } catch(e) {}
    }

    async snmpClearAlerts() {
        await this.api.request('/api/snmp/alerts/clear', {method: 'POST'});
        this.snmpLoadAlerts();
        Toast.success('Alerts cleared');
    }
}


var app = new NetConfigApp();
app.init();
