"use strict";
const tools = JSON.parse(document.getElementById("tool-data").textContent);
const officeReady = document.querySelector('meta[name="office-ready"]').content === "true";
const token = document.querySelector('meta[name="ihatepdf-token"]').content;
const $ = id => document.getElementById(id);
const paths = {
  grid:'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  file:'<path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>',
  merge:'<path d="M4 4h6v7H4zM14 4h6v7h-6zM7 14v3h10v-3M12 17v4"/>',
  split:'<path d="M7 3h10v6H7zM12 9v4M5 17v-4h14v4M2 17h6v4H2zM16 17h6v4h-6z"/>',
  trim:'<path d="M8 4H4v4M16 4h4v4M4 16v4h4M20 16v4h-4"/><rect x="8" y="7" width="8" height="10" rx="1"/>',
  delete:'<path d="M5 7h14M9 7V4h6v3M7 7l1 14h8l1-14M10 11v6M14 11v6"/>',
  reorder:'<path d="M8 4v16M5 7l3-3 3 3M16 20V4M13 17l3 3 3-3"/>',
  rotate:'<path d="M4 10a8 8 0 1 1 1 8M4 4v6h6"/>',
  crop:'<path d="M7 3v14h14M3 7h14v14M10 3v2M3 10h2"/>',
  image:'<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="8" cy="9" r="1.5"/><path d="m3 17 5-5 4 4 3-3 6 6"/>',
  word:'<path d="M14 3H6v18h12V7zM14 3v5h4"/><path d="m8 11 1.5 6 2-5 2 5 1.5-6"/>',
  slides:'<rect x="3" y="4" width="18" height="13" rx="1"/><path d="M12 17v4M7 21h10M7 9h10M7 12h6"/>',
  office:'<rect x="4" y="3" width="16" height="18" rx="1"/><path d="M4 9h16M4 15h16M10 9v12"/>',
  text:'<path d="M5 4h14M12 4v16M8 20h8M5 4v3M19 4v3"/>',
  compress:'<path d="M3 8h5V3M8 8 3 3M21 16h-5v5M16 16l5 5M14 3h7v7M3 14v7h7"/>',
  watermark:'<path d="M12 3S5 10 5 15a7 7 0 0 0 14 0c0-5-7-12-7-12zM8 16a4 4 0 0 0 4 3"/>',
  number:'<path d="M10 3 8 21M17 3l-2 18M4 9h17M3 15h17"/>',
  lock:'<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3"/>',
  unlock:'<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 7.5-2M12 14v3"/>',
  info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/>',
  shield:'<path d="M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6z"/><path d="m8 12 3 3 5-6"/>',
  search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  arrow:'<path d="M4 12h16M15 7l5 5-5 5"/>',
  back:'<path d="M20 12H4M9 7l-5 5 5 5"/>',
  chevron:'<path d="m6 9 6 6 6-6"/>',
  upload:'<path d="M12 16V3M7 8l5-5 5 5M4 15v6h16v-6"/>',
  download:'<path d="M12 3v13M7 11l5 5 5-5M4 17v4h16v-4"/>',
  close:'<path d="m6 6 12 12M18 6 6 18"/>',
  up:'<path d="m6 14 6-6 6 6"/>',
  down:'<path d="m6 10 6 6 6-6"/>'
};
const icon = name => `<svg viewBox="0 0 24 24" aria-hidden="true">${paths[name] || paths.file}</svg>`;
const element = (tag, className, text) => { const node = document.createElement(tag); if (className) node.className = className; if (text !== undefined) node.textContent = text; return node; };
const size = bytes => bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
let selected = null, files = [], category = "All", busy = false;
document.querySelectorAll("[data-icon]").forEach(node => node.innerHTML = icon(node.dataset.icon));

for (const group of ["Organize", "Convert", "Enhance", "Security"]) {
  $("tool-nav").append(element("div", "nav-group", group));
  for (const tool of tools.filter(tool => tool.category === group)) {
    const button = element("button", "nav-tool"); button.type = "button"; button.dataset.tool = tool.id;
    button.innerHTML = icon(tool.icon); button.append(element("span", "", tool.title));
    button.addEventListener("click", () => selectTool(tool.id)); $("tool-nav").append(button);
  }
}
function renderCatalog() {
  const query = $("search").value.toLowerCase().trim(); $("tool-grid").replaceChildren();
  for (const tool of tools.filter(tool => (category === "All" || category === tool.category) && `${tool.title} ${tool.description}`.toLowerCase().includes(query))) {
    const button = element("button", "tool-card"); button.type = "button";
    const mark = element("span", `tool-icon ${tool.category.toLowerCase()}`); mark.innerHTML = icon(tool.icon);
    const arrow = element("span", "card-arrow"); arrow.innerHTML = icon("arrow");
    button.append(mark, arrow, element("h2", "", tool.title), element("p", "", tool.description));
    button.addEventListener("click", () => selectTool(tool.id)); $("tool-grid").append(button);
  }
  $("empty-search").hidden = $("tool-grid").children.length > 0;
}
function showHome() {
  if (busy) return; selected = null; $("home").hidden = false; $("workspace").hidden = true;
  $("breadcrumb").textContent = "Your PDF workspace"; $("all-tools").classList.add("active");
  document.querySelectorAll(".nav-tool").forEach(node => node.classList.remove("active"));
}
function selectTool(id) {
  if (busy) return;
  selected = tools.find(tool => tool.id === id); files = []; $("process-form").reset();
  $("home").hidden = true; $("workspace").hidden = false; $("results").hidden = true; $("error").hidden = true;
  $("all-tools").classList.remove("active"); document.querySelectorAll(".nav-tool").forEach(node => node.classList.toggle("active", node.dataset.tool === id));
  $("breadcrumb").textContent = `${selected.category} / ${selected.title}`; $("tool-title").textContent = selected.title; $("tool-description").textContent = selected.description;
  $("selected-icon").className = `tool-icon ${selected.category.toLowerCase()}`; $("selected-icon").innerHTML = icon(selected.icon);
  $("action-text").textContent = selected.action; $("office-note").hidden = !selected.office || officeReady;
  const accepts = { pdf:".pdf", images:".jpg,.jpeg,.png,.webp,.bmp,.tif,.tiff,.gif", word:".doc,.docx,.odt,.rtf", ppt:".ppt,.pptx,.odp", office:".doc,.docx,.odt,.rtf,.ppt,.pptx,.odp,.xls,.xlsx,.ods" };
  $("files").accept = accepts[selected.input || "pdf"];
  $("input-kind").textContent = {pdf:"PDF files",images:"Images",word:"Word documents",ppt:"Presentations",office:"Office documents"}[selected.input || "pdf"];
  $("password-field").hidden = selected.office || selected.input === "images";
  $("font-field").hidden = !["watermark", "number"].includes(id);
  $("advanced").hidden = selected.office || selected.input === "images"; $("advanced").open = id === "unlock";
  $("settings-hint").textContent = id === "crop" ? "Cropping changes the visible area; content outside it remains in the file." : id === "compress" ? "Savings depend on your document. Already optimized files may grow." : id === "text" ? "Reads existing text. Image-only pages contain no extractable text." : !selected.fields.length ? "Ready to go. No extra settings needed." : "";
  $("tool-fields").replaceChildren();
  for (const field of selected.fields) {
    const wrapper = element("div", "field"); wrapper.dataset.field = field.name;
    const label = element("label", "", field.label); label.htmlFor = `option-${field.name}`;
    const input = document.createElement(field.type === "select" ? "select" : "input"); input.id = `option-${field.name}`; input.name = field.name;
    if (field.type === "select") for (const [value, text] of field.choices) { const option = element("option", "", text); option.value = value; input.append(option); }
    else { input.type = field.type; for (const key of ["min", "max", "step"]) if (field[key] !== undefined) input[key] = field[key]; if (field.type === "password") input.autocomplete = "new-password"; }
    input.value = field.default; input.required = !!field.required; wrapper.append(label, input);
    if (field.hint) wrapper.append(element("small", "", field.hint)); $("tool-fields").append(wrapper);
    input.addEventListener("change", updateConditionalFields);
  }
  updateConditionalFields(); renderFiles(); window.scrollTo({top:0,behavior:"instant"});
}
function updateConditionalFields() {
  if (!selected) return;
  for (const field of selected.fields) {
    const wrapper = $("tool-fields").querySelector(`[data-field="${field.name}"]`);
    const hidden = field.when && Object.entries(field.when).some(([key,value]) => $(`option-${key}`).value !== value);
    wrapper.hidden = !!hidden; $(`option-${field.name}`).disabled = !!hidden;
  }
  const imageMode = selected.id === "watermark" && $("option-watermark_type").value === "image";
  $("image-field").hidden = !imageMode; $("watermark-image").required = imageMode;
}
function addFiles(incoming) {
  if (busy || !selected) return;
  const extensions = $("files").accept.split(",");
  const rejected = [...incoming].filter(file => !extensions.includes(`.${file.name.split(".").pop().toLowerCase()}`));
  if (rejected.length) { showError(`Choose ${$("input-kind").textContent.toLowerCase()} for this tool.`); return; }
  if (files.length + incoming.length > 100) { showError("Choose up to 100 files per operation."); return; }
  const combined = [...files, ...incoming];
  if (combined.reduce((total,file) => total + file.size, 0) > 255 * 1024 * 1024) { showError("Choose less than 256 MB per operation."); return; }
  files = combined; $("error").hidden = true; $("results").hidden = true; renderFiles();
}
function renderFiles() {
  $("file-list").replaceChildren();
  files.forEach((file,index) => {
    const row = element("div", "file-row"); const mark = element("span"); mark.innerHTML = icon("file");
    const info = element("div", "file-info"); info.append(element("div", "file-name", file.name),element("div", "file-size", size(file.size))); row.append(mark,info);
    if (selected.combine) for (const [name,delta] of [["up",-1],["down",1]]) {
      const button = element("button", "icon-button"); button.type = "button"; button.innerHTML = icon(name); button.setAttribute("aria-label", `Move ${file.name} ${name}`); button.disabled = busy || index + delta < 0 || index + delta >= files.length;
      button.addEventListener("click", () => { [files[index], files[index+delta]] = [files[index+delta], files[index]]; renderFiles(); }); row.append(button);
    }
    const remove = element("button", "icon-button"); remove.type = "button"; remove.innerHTML = icon("close"); remove.setAttribute("aria-label", `Remove ${file.name}`); remove.disabled = busy;
    remove.addEventListener("click", () => { files.splice(index,1); renderFiles(); }); row.append(remove); $("file-list").append(row);
  });
  $("file-actions").hidden = !files.length; $("order-hint").hidden = !selected.combine || files.length < 2;
  $("file-summary").textContent = `${files.length} file${files.length === 1 ? "" : "s"} · ${size(files.reduce((total,file)=>total+file.size,0))}${files.length > 1 && !selected.combine ? " · Batch processing" : ""}`;
  $("process-button").disabled = busy || !files.length;
}
function showError(message) { $("error").textContent = message; $("error").hidden = false; }
function renderResults(data) {
  $("result-title").textContent = data.errors.length ? "Your results are ready, with a few issues." : "Your files are ready.";
  $("download-all").href = data.files.length === 1 ? data.files[0].url : data.archive;
  $("download-all").replaceChildren(document.createTextNode(data.files.length === 1 ? "Download file" : "Download all"));
  const arrow = element("span"); arrow.innerHTML = icon("download"); $("download-all").append(arrow);
  $("result-notes").replaceChildren(); for (const message of data.notes) $("result-notes").append(element("p", "result-note", message));
  for (const message of data.errors) $("result-notes").append(element("p", "result-note warning", message));
  $("result-files").replaceChildren();
  for (const file of data.files) {
    const row = element("div", "result-row"); const info = element("div", "file-info"); info.append(element("div", "file-name",file.name),element("div", "file-size",size(file.size)));
    const link = element("a", "download-link", "Download"); link.href = file.url; const mark = element("span"); mark.innerHTML = icon("download"); link.append(mark); row.append(info,link); $("result-files").append(row);
  }
  $("result-details").replaceChildren();
  for (const info of data.details) {
    $("result-details").append(element("h3", "", info.file)); const stats = element("div", "detail-summary");
    for (const [value,label] of [[info.pages,"Pages"],[size(info.bytes),"File size"],[info.encrypted ? "Protected" : "Open","Protection"]]) { const stat = element("div", "detail-stat"); stat.append(element("strong","",String(value)),element("span","",label)); stats.append(stat); } $("result-details").append(stats);
    if (info.locked) $("result-details").append(element("p", "result-note", "Enter the PDF password to view the remaining details."));
    if (info.metadata) { const table = element("table", "details-table"); for (const [key,value] of Object.entries(info.metadata).filter(([key,value]) => value)) { const row = element("tr"); row.append(element("th","",key),element("td","",String(value))); table.append(row); } $("result-details").append(table); }
    if (info.page_sizes) { const table = element("table", "details-table"); const heading = element("tr"); for (const title of ["Page","Size (points)","Rotation"]) heading.append(element("th","",title)); table.append(heading); for (const page of info.page_sizes) { const row = element("tr"); for (const text of [page.page, `${page.width_pt.toFixed(1)} × ${page.height_pt.toFixed(1)}`, `${page.rotation}°`]) row.append(element("td","",String(text))); table.append(row); } $("result-details").append(table); }
  }
  $("results").hidden = false; $("results").scrollIntoView({behavior:"smooth",block:"nearest"});
}
$("process-form").addEventListener("submit", async event => {
  event.preventDefault(); if (busy || !files.length) return;
  const options = Object.fromEntries(new FormData($("process-form"))); options.password = $("input-password").value;
  if (selected.id === "encrypt" && options.new_password !== options.confirm_password) { showError("The new passwords do not match."); return; }
  const payload = new FormData(); payload.append("tool",selected.id); payload.append("options",JSON.stringify(options)); for (const file of files) payload.append("files",file);
  if (!$("image-field").hidden && $("watermark-image").files[0]) payload.append("watermark_image",$("watermark-image").files[0]);
  if (!$("font-field").hidden && $("font").files[0]) payload.append("font",$("font").files[0]);
  busy = true; $("error").hidden = true; $("results").hidden = true; $("action-text").textContent = "Working…";
  const spinner = element("span", "busy-indicator"); spinner.id = "spinner"; $("process-button").append(spinner);
  $("process-form").setAttribute("aria-busy","true"); renderFiles();
  const lockedControls = [...$("process-form").querySelectorAll("input,select,button,summary")].filter(node=>!node.disabled);
  lockedControls.forEach(node=>node.disabled=true);
  try {
    const response = await fetch("/api/process",{method:"POST",headers:{"X-IhatePDF-Token":token},body:payload}); const data = await response.json();
    if (!response.ok) throw new Error(data.error || "The files could not be processed."); renderResults(data);
    $("process-form").querySelectorAll('input[type="password"]').forEach(input=>input.value="");
  } catch (error) { showError(error.message === "Failed to fetch" ? "The local app is unavailable. Start run.py and refresh this page." : error.message); }
  finally { busy=false; lockedControls.forEach(node=>node.disabled=false); updateConditionalFields(); $("process-form").removeAttribute("aria-busy"); $("spinner").remove(); $("action-text").textContent=selected.action; renderFiles(); }
});
$("files").addEventListener("change",event=>{addFiles(event.target.files);event.target.value="";});
$("dropzone").addEventListener("click",()=>{if(!busy)$("files").click();});
$("dropzone").addEventListener("keydown",event=>{if(["Enter"," "].includes(event.key)){event.preventDefault();if(!busy)$("files").click();}});
for(const name of ["dragenter","dragover"])$("dropzone").addEventListener(name,event=>{event.preventDefault();if(!busy)$("dropzone").classList.add("drag-over");});
for(const name of ["dragleave","drop"])$("dropzone").addEventListener(name,event=>{event.preventDefault();$("dropzone").classList.remove("drag-over");});
$("dropzone").addEventListener("drop",event=>addFiles(event.dataTransfer.files));
$("add-files").addEventListener("click",()=>$("files").click()); $("clear-files").addEventListener("click",()=>{files=[];renderFiles();});
$("back").addEventListener("click",showHome); $("all-tools").addEventListener("click",showHome); document.querySelector(".brand").addEventListener("click",event=>{event.preventDefault();showHome();});
$("search").addEventListener("input",renderCatalog); $("filters").addEventListener("click",event=>{const button=event.target.closest("button");if(!button)return;category=button.dataset.category;document.querySelectorAll(".filter").forEach(node=>node.classList.toggle("active",node===button));renderCatalog();});
renderCatalog();

