// Admin form behaviors: tabs, slug/canonical autogeneration, SunEditor upload hook

(function(){
  function translit(str){
    const map = {
      'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z','и':'i','й':'y','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f','х':'h','ц':'c','ч':'ch','ш':'sh','щ':'sch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya',
      'А':'a','Б':'b','В':'v','Г':'g','Д':'d','Е':'e','Ё':'e','Ж':'zh','З':'z','И':'i','Й':'y','К':'k','Л':'l','М':'m','Н':'n','О':'o','П':'p','Р':'r','С':'s','Т':'t','У':'u','Ф':'f','Х':'h','Ц':'c','Ч':'ch','Ш':'sh','Щ':'sch','Ъ':'','Ы':'y','Ь':'','Э':'e','Ю':'yu','Я':'ya'
    };
    return str.split('').map(ch=>map[ch]!==undefined?map[ch]:ch).join('');
  }

  function slugify(value){
    return translit(String(value||''))
      .toLowerCase()
      .replace(/[^a-z0-9\s-]/g,'')
      .trim()
      .replace(/\s+/g,'-')
      .replace(/-+/g,'-');
  }

  document.addEventListener('DOMContentLoaded', function(){
    // tabs
    document.querySelectorAll('.tab-nav button').forEach(btn=>{
      btn.addEventListener('click', ()=>{
        document.querySelectorAll('.tab-nav button').forEach(b=>b.classList.remove('active'));
        document.querySelectorAll('.tab-panel').forEach(p=>p.classList.remove('active'));
        btn.classList.add('active');
        const id = btn.getAttribute('data-tab');
        const panel = document.getElementById(id);
        if(panel) panel.classList.add('active');
      });
    });

    // slug + canonical auto
    const titleInput = document.querySelector('input[name="title"]');
    const slugInput = document.querySelector('input[name="slug"]');
    const canonicalInput = document.querySelector('input[name="canonical_url"]');
    function updateSlug(){ if(!slugInput) return; slugInput.value = slugify(titleInput.value); updateCanonical(); }
    function updateCanonical(){ if(!canonicalInput || !slugInput) return; canonicalInput.value = '/' + slugInput.value; }
    if(titleInput){ titleInput.addEventListener('input', updateSlug); }

    // SunEditor init with upload hook
    if(window.SUNEDITOR){
      const editor = SUNEDITOR.create('content', {
        height: '900px',
        resizingBar: true,
        defaultStyle: 'font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,Ubuntu; font-size:16px;',
        buttonList: [
          ['undo','redo'],
          ['formatBlock','bold','italic','underline','strike'],
          ['align','list','indent','outdent'],
          ['link','image','video','table'],
          ['removeFormat','codeView','fullScreen']
        ],
        lang: window.SUNEDITOR_LANG && SUNEDITOR_LANG.ru ? SUNEDITOR_LANG.ru : undefined,
      });
      editor.setOptions({ imageUploadUrl: '/admin/upload-image' });
      editor.onImageUpload = async function(files, info, uploadHandler){
        const form = new FormData();
        for(const f of files) form.append('files', f);
        const res = await fetch('/admin/upload-image', { method: 'POST', body: form });
        const data = await res.json();
        const result = { result: (data.urls||[]).map(u=>({ url: u, name: 'image', size: 0, alt: '' })) };
        uploadHandler(result);
      };
      const form = document.querySelector('form');
      if(form){ form.addEventListener('submit', ()=> editor.save()); }
    }

    // Cover image file → upload then fill URL field
    const coverInputText = document.querySelector('input[name="cover_image_url"]');
    const coverFile = document.getElementById('coverUpload');
    if(coverFile && coverInputText){
      coverFile.addEventListener('change', async ()=>{
        if(!coverFile.files || coverFile.files.length===0) return;
        const form = new FormData();
        for(const f of coverFile.files) form.append('files', f);
        const res = await fetch('/admin/upload-image', { method: 'POST', body: form });
        const data = await res.json();
        if(data.urls && data.urls.length>0){ coverInputText.value = data.urls[0]; }
      });
    }
  });
})();


