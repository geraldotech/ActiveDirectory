const state = { users: [], ous: [], groups: [], section: 'dashboard' };
const formModal = new bootstrap.Modal('#formModal');
const detailModal = new bootstrap.Modal('#detailModal');
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const esc = value => String(value ?? '').replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
const urlId = value => encodeURIComponent(value);

async function api(path, options = {}) {
  $('#connectionState').textContent = 'Working…';
  const response = await fetch(`/api${path}`, {
    headers: {'Content-Type': 'application/json', ...(options.headers || {})},
    ...options
  });
  let payload;
  try { payload = await response.json(); } catch { payload = {error: `HTTP ${response.status}`}; }
  $('#connectionState').textContent = response.ok ? 'Connected' : 'Error';
  $('#connectionState').className = `badge ${response.ok ? 'text-bg-success' : 'text-bg-danger'}`;
  if (!response.ok) throw new Error(payload.error || 'The directory operation failed');
  return payload;
}

function notify(message, kind = 'success') {
  const alert = document.createElement('div');
  alert.className = `alert alert-${kind} alert-dismissible shadow`;
  alert.innerHTML = `${esc(message)}<button class="btn-close" data-bs-dismiss="alert"></button>`;
  $('#alertArea').append(alert);
  setTimeout(() => alert.remove(), 5500);
}

function busyRow(table, columns) { $(`#${table} tbody`).innerHTML = `<tr><td colspan="${columns}" class="empty"><span class="spinner-border spinner-border-sm me-2"></span>Loading directory…</td></tr>`; }
function emptyRow(columns, label) { return `<tr><td colspan="${columns}" class="empty">No ${label} found.</td></tr>`; }

async function loadDashboard() {
  $$('[data-metric]').forEach(node => node.textContent = '—');
  try {
    const {data} = await api('/dashboard');
    Object.entries(data).forEach(([key, value]) => { const node = $(`[data-metric="${key}"]`); if (node) node.textContent = value; });
  } catch (error) { notify(error.message, 'danger'); }
}

async function loadUsers() {
  busyRow('usersTable', 6);
  try {
    const result = await api('/users'); state.users = result.data;
    $('#usersTable tbody').innerHTML = state.users.length ? state.users.map(user => `<tr>
      <td><strong>${esc(user.name)}</strong></td><td>${esc(user.username)}</td><td>${esc(user.upn)}</td>
      <td><span class="truncate" title="${esc(user.ou)}">${esc(user.ou)}</span></td>
      <td><span class="status-badge ${user.enabled ? 'badge-enabled' : 'badge-disabled'}">${user.enabled ? 'Enabled' : 'Disabled'}</span></td>
      <td class="text-end"><button class="btn btn-sm btn-outline-primary" data-view-user="${esc(user.id)}">Manage</button></td></tr>`).join('') : emptyRow(6, 'users');
  } catch (error) { $('#usersTable tbody').innerHTML = emptyRow(6, 'users'); notify(error.message, 'danger'); }
}

async function loadOus() {
  busyRow('ousTable', 4);
  try {
    const result = await api('/ous'); state.ous = result.data;
    $('#ousTable tbody').innerHTML = state.ous.length ? state.ous.map(ou => `<tr><td><strong>${esc(ou.name)}</strong></td><td><span class="truncate" title="${esc(ou.dn)}">${esc(ou.dn)}</span></td><td><span class="truncate">${esc(ou.parentOu)}</span></td><td class="text-end"><button class="btn btn-sm btn-outline-primary" data-view-ou="${esc(ou.id)}">View</button></td></tr>`).join('') : emptyRow(4, 'OUs');
  } catch (error) { $('#ousTable tbody').innerHTML = emptyRow(4, 'OUs'); notify(error.message, 'danger'); }
}

async function loadGroups() {
  busyRow('groupsTable', 5);
  try {
    const result = await api('/groups'); state.groups = result.data;
    $('#groupsTable tbody').innerHTML = state.groups.length ? state.groups.map(group => `<tr><td><strong>${esc(group.name)}</strong></td><td><span class="truncate" title="${esc(group.dn)}">${esc(group.dn)}</span></td><td>${esc(group.type)}</td><td>${group.members.length}</td><td class="text-end"><button class="btn btn-sm btn-outline-primary" data-view-group="${esc(group.id)}">Manage</button></td></tr>`).join('') : emptyRow(5, 'groups');
  } catch (error) { $('#groupsTable tbody').innerHTML = emptyRow(5, 'groups'); notify(error.message, 'danger'); }
}

const loaders = {dashboard: loadDashboard, users: loadUsers, ous: loadOus, groups: loadGroups};
function selectSection(name) {
  state.section = name;
  $$('.page-section').forEach(section => section.classList.toggle('active', section.id === name));
  $$('.sidebar .nav-link').forEach(link => link.classList.toggle('active', link.dataset.section === name));
  loaders[name]();
}

function ouOptions(selected = '') {
  return `<option value="">Select an OU…</option>${state.ous.map(ou => `<option value="${esc(ou.dn)}" ${ou.dn === selected ? 'selected' : ''}>${esc(ou.name)} — ${esc(ou.dn)}</option>`).join('')}`;
}
function field(name, label, value = '', options = {}) {
  const type = options.type || 'text'; const required = options.required ? 'required' : '';
  if (type === 'textarea') return `<div class="col-12"><label class="form-label">${label}</label><textarea class="form-control" name="${name}" ${required}>${esc(value)}</textarea></div>`;
  if (type === 'select') return `<div class="${options.wide ? 'col-12' : 'col-md-6'}"><label class="form-label">${label}</label><select class="form-select" name="${name}" ${required}>${options.html}</select></div>`;
  return `<div class="${options.wide ? 'col-12' : 'col-md-6'}"><label class="form-label">${label}</label><input class="form-control" type="${type}" name="${name}" value="${esc(value)}" ${required} ${options.minlength ? `minlength="${options.minlength}"` : ''}></div>`;
}

function accountOptions(user) {
  const checked = value => value ? 'checked' : '';
  return `<div class="col-12"><fieldset class="account-options"><legend>Account options</legend>
    ${user.locked ? `<div class="form-check mb-2"><input class="form-check-input" type="checkbox" name="unlockAccount" id="unlockAccount"><label class="form-check-label" for="unlockAccount">Unlock account</label></div>` : ''}
    <div class="form-check"><input class="form-check-input" type="checkbox" name="mustChangePassword" id="mustChangePassword" ${checked(user.mustChangePassword)}><label class="form-check-label" for="mustChangePassword">User must change password at next logon</label></div>
    <div class="form-check"><input class="form-check-input" type="checkbox" id="cannotChangePassword" disabled><label class="form-check-label text-secondary" for="cannotChangePassword">User cannot change password <small>(permission management not available)</small></label></div>
    <div class="form-check"><input class="form-check-input" type="checkbox" name="passwordNeverExpires" id="passwordNeverExpires" ${checked(user.passwordNeverExpires)}><label class="form-check-label" for="passwordNeverExpires">Password never expires</label></div>
    <div class="form-check"><input class="form-check-input" type="checkbox" name="reversiblePasswordEncryption" id="reversiblePasswordEncryption" ${checked(user.reversiblePasswordEncryption)}><label class="form-check-label" for="reversiblePasswordEncryption">Store password using reversible encryption</label></div>
  </fieldset></div>
  <div class="col-12"><fieldset class="account-options"><legend>Account expires</legend>
    <div class="form-check"><input class="form-check-input" type="radio" name="expirationMode" id="expiresNever" value="never" ${checked(!user.accountExpires)}><label class="form-check-label" for="expiresNever">Never</label></div>
    <div class="d-flex align-items-center gap-2 mt-2"><div class="form-check"><input class="form-check-input" type="radio" name="expirationMode" id="expiresOn" value="date" ${checked(Boolean(user.accountExpires))}><label class="form-check-label" for="expiresOn">End of:</label></div><input class="form-control account-expiry-date" type="date" name="accountExpires" value="${esc(user.accountExpires)}"></div>
  </fieldset></div>`;
}

async function ensureLookups() {
  const jobs = [];
  if (!state.ous.length) jobs.push(api('/ous').then(r => state.ous = r.data));
  if (!state.users.length) jobs.push(api('/users').then(r => state.users = r.data));
  await Promise.all(jobs);
}

async function openForm(kind, object = null) {
  try { await ensureLookups(); } catch (error) { notify(error.message, 'danger'); return; }
  const editing = Boolean(object); const form = $('#objectForm');
  form.dataset.kind = kind; form.dataset.id = object?.id || ''; form.dataset.editing = editing;
  $('.modal-title', $('#formModal')).textContent = `${editing ? 'Edit' : 'Create'} ${kind === 'ou' ? 'organizational unit' : kind}`;
  let html = '';
  if (kind === 'user') html = field('name','Display name',object?.name,{required:true}) + field('username','Username / sAMAccountName',object?.username,{required:true}) + field('firstName','First name',object?.firstName) + field('lastName','Last name',object?.lastName) + field('upn','User principal name',object?.upn) + field('email','Email',object?.email,{type:'email'}) + (!editing ? field('ouDn','Organizational unit','',{type:'select',html:ouOptions(),required:true,wide:true}) + field('password','Initial password','',{type:'password',required:true,minlength:8}) + `<div class="col-md-6 d-flex align-items-end pb-2"><div class="form-check"><input class="form-check-input" type="checkbox" name="enabled" id="enabled" checked><label class="form-check-label" for="enabled">Enable account</label></div></div>` : accountOptions(object)) + field('description','Description',object?.description,{type:'textarea'});
  if (kind === 'ou') html = field('name','OU name','',{required:true}) + field('parentDn','Parent OU','',{type:'select',html:`<option value="">Directory root</option>${ouOptions().replace('<option value="">Select an OU…</option>','')}`,wide:true}) + field('description','Description','',{type:'textarea'});
  if (kind === 'group') html = field('name','Group name',object?.name,{required:true}) + field('username','sAMAccountName',object?.username) + (!editing ? field('ouDn','Organizational unit','',{type:'select',html:ouOptions(),required:true,wide:true}) : '') + field('groupType','Group type',object?.groupType || -2147483646,{type:'select',html:`<option value="-2147483646">Global / Security</option><option value="-2147483644">Domain Local / Security</option><option value="-2147483640">Universal / Security</option><option value="2">Global / Distribution</option><option value="4">Domain Local / Distribution</option><option value="8">Universal / Distribution</option>`,wide:true}) + field('description','Description',object?.description,{type:'textarea'});
  $('#formFields').innerHTML = `<div class="row g-3">${html}</div>`; formModal.show();
}

$('#objectForm').addEventListener('submit', async event => {
  event.preventDefault(); const form = event.currentTarget; const submit = $('button[type="submit"]', form);
  const editing = form.dataset.editing === 'true';
  const data = Object.fromEntries(new FormData(form).entries());
  if (form.dataset.kind === 'user' && !editing) data.enabled = Boolean(form.elements.enabled.checked);
  if (form.dataset.kind === 'user' && editing) {
    for (const name of ['mustChangePassword', 'passwordNeverExpires', 'reversiblePasswordEncryption', 'unlockAccount']) data[name] = Boolean(form.elements[name]?.checked);
    data.accountExpires = form.elements.expirationMode.value === 'date' ? form.elements.accountExpires.value : '';
    if (form.elements.expirationMode.value === 'date' && !data.accountExpires) return notify('Select the account expiration date', 'warning');
  }
  if ('groupType' in data) data.groupType = Number(data.groupType);
  const plural = form.dataset.kind === 'user' ? 'users' : form.dataset.kind === 'ou' ? 'ous' : 'groups';
  const path = editing ? `/${plural}/${urlId(form.dataset.id)}` : `/${plural}`;
  submit.disabled = true;
  try {
    const result = await api(path, {method: editing ? 'PUT' : 'POST', body: JSON.stringify(data)});
    formModal.hide(); notify(result.message); await loaders[plural]();
  } catch (error) { notify(error.message, 'danger'); } finally { submit.disabled = false; }
});

function details(rows) { return `<dl class="detail-grid">${rows.map(([key,value]) => `<dt>${esc(key)}</dt><dd>${Array.isArray(value) ? (value.length ? value.map(esc).join('<br>') : 'None') : esc(value || '—')}</dd>`).join('')}</dl>`; }
function showOu(ou) { $('.modal-title', $('#detailModal')).textContent = ou.name; $('#detailBody').innerHTML = details([['OU name',ou.name],['Distinguished name',ou.dn],['Parent OU',ou.parentOu],['Description',ou.description]]); detailModal.show(); }
function showUser(user) {
  $('.modal-title', $('#detailModal')).textContent = user.name;
  $('#detailBody').innerHTML = details([['Username',user.username],['User principal name',user.upn],['Distinguished name',user.dn],['OU',user.ou],['Account status',user.enabled?'Enabled':'Disabled'],['Email',user.email],['Description',user.description],['Group memberships',user.groups]]) + `<hr><div class="d-flex flex-wrap gap-2"><button class="btn btn-primary" data-edit-user>Edit user</button><button class="btn btn-outline-${user.enabled?'danger':'success'}" data-toggle-user>${user.enabled?'Disable':'Enable'} account</button><button class="btn btn-outline-secondary" data-password-user>Reset password</button></div>`;
  $('#detailBody').dataset.object = JSON.stringify(user); detailModal.show();
}
function showGroup(group) {
  $('.modal-title', $('#detailModal')).textContent = group.name;
  const available = state.users.map(user => `<option value="${esc(user.id)}">${esc(user.name)} (${esc(user.username)})</option>`).join('');
  $('#detailBody').innerHTML = details([['Group name',group.name],['sAMAccountName',group.username],['Distinguished name',group.dn],['Group type',group.type],['Description',group.description]]) + `<hr><h3 class="fs-6">Members (${group.members.length})</h3><div class="member-list mb-3">${group.members.length ? group.members.map(member => `<div class="member-row"><span>${esc(member)}</span><button class="btn btn-sm btn-link text-danger p-0" data-remove-member="${esc(member)}">Remove</button></div>`).join('') : '<div class="text-secondary p-2">No members</div>'}</div><div class="input-group"><select class="form-select" id="memberUser"><option value="">Select a user…</option>${available}</select><button class="btn btn-outline-primary" data-add-member>Add user</button></div><hr><button class="btn btn-primary" data-edit-group>Edit group</button>`;
  $('#detailBody').dataset.object = JSON.stringify(group); detailModal.show();
}

document.addEventListener('click', async event => {
  const section = event.target.closest('[data-section]'); if (section) return selectSection(section.dataset.section);
  const create = event.target.closest('[data-create]'); if (create) return openForm(create.dataset.create);
  const refresh = event.target.closest('[data-refresh]'); if (refresh) return loaders[refresh.dataset.refresh]();
  const userButton = event.target.closest('[data-view-user]'); if (userButton) return showUser(state.users.find(x => x.id === userButton.dataset.viewUser));
  const ouButton = event.target.closest('[data-view-ou]'); if (ouButton) return showOu(state.ous.find(x => x.id === ouButton.dataset.viewOu));
  const groupButton = event.target.closest('[data-view-group]'); if (groupButton) { await ensureLookups(); return showGroup(state.groups.find(x => x.id === groupButton.dataset.viewGroup)); }
  const detailObject = $('#detailBody').dataset.object ? JSON.parse($('#detailBody').dataset.object) : null;
  if (event.target.closest('[data-edit-user]')) { detailModal.hide(); return openForm('user', detailObject); }
  if (event.target.closest('[data-edit-group]')) { detailModal.hide(); return openForm('group', detailObject); }
  if (event.target.closest('[data-toggle-user]')) try { const result = await api(`/users/${urlId(detailObject.id)}/status`, {method:'PATCH',body:JSON.stringify({enabled:!detailObject.enabled})}); notify(result.message); detailModal.hide(); loadUsers(); } catch(error) { notify(error.message,'danger'); }
  if (event.target.closest('[data-password-user]')) { const password = prompt('Enter the new password (at least 8 characters):'); if (!password) return; try { const result = await api(`/users/${urlId(detailObject.id)}/password`, {method:'POST',body:JSON.stringify({password})}); notify(result.message); } catch(error) { notify(error.message,'danger'); } }
  if (event.target.closest('[data-add-member]')) { const userId = $('#memberUser').value; if (!userId) return notify('Select a user first','warning'); await changeMember(detailObject,userId,true); }
  const remove = event.target.closest('[data-remove-member]'); if (remove) await changeMember(detailObject,remove.dataset.removeMember,false);
});

async function changeMember(group, userId, add) {
  try { const result = await api(`/groups/${urlId(group.id)}/members`, {method:add?'POST':'DELETE',body:JSON.stringify({userId})}); notify(result.message); state.groups = state.groups.map(item => item.id === result.data.id ? result.data : item); showGroup(result.data); loadGroups(); } catch(error) { notify(error.message,'danger'); }
}

$$('[data-search]').forEach(input => input.addEventListener('input', () => {
  const term = input.value.toLowerCase(); $$(`#${input.dataset.search} tbody tr`).forEach(row => row.hidden = !row.textContent.toLowerCase().includes(term));
}));

loadDashboard();
