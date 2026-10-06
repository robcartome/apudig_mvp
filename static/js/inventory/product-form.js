(function () {
  'use strict';

  function initRemoteSelect2(el) {
    const url         = el.dataset.url;
    const hiddenId    = el.dataset.hiddenId;
    const placeholder = el.dataset.placeholder || 'Buscar…';
    const $el = $(el);

    $el.select2({
      theme: 'bootstrap-5',
      width: '100%',
      dropdownParent: $('body'),
      placeholder: placeholder,
      allowClear: true,
      minimumInputLength: 0,
      ajax: {
        transport: function (params, success, failure) {
          window.ApiService.get(url + '?q=' + encodeURIComponent(params.data.term || ''))
            .then(success)
            .catch(failure);
        },
        processResults: function (data) {
          return { results: data.results || [] };
        },
        delay: 250,
      },
    });

    $el.on('select2:select', function (e) {
      document.getElementById(hiddenId).value = e.params.data.id || '';
    });
    $el.on('select2:unselect select2:clear', function () {
      document.getElementById(hiddenId).value = '';
    });
  }

  document.querySelectorAll('.remote-select-js').forEach(initRemoteSelect2);

  const MAX_IMAGE_DIMENSION = 1920;
  const TARGET_IMAGE_SIZE = 1.2 * 1024 * 1024;
  const MAX_TOTAL_IMAGE_SIZE = 4 * 1024 * 1024;
  const INITIAL_JPEG_QUALITY = 0.84;
  const MIN_JPEG_QUALITY = 0.63;
  const SUPPORTED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp'];
  const HEIC_IMAGE_TYPES = ['image/heic', 'image/heif'];
  const productForm = document.querySelector('form[enctype="multipart/form-data"]');
  let pendingImageProcesses = 0;

  function updateFormBusyState() {
    if (!productForm) return;
    productForm.querySelectorAll('button[type="submit"]').forEach(function (button) {
      button.disabled = pendingImageProcesses > 0;
    });
  }

  function formatBytes(bytes) {
    if (bytes < 1024 * 1024) return Math.max(1, Math.round(bytes / 1024)) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  }

  function fileExtension(file) {
    const match = (file.name || '').toLowerCase().match(/\.([a-z0-9]+)$/);
    return match ? match[1] : '';
  }

  function detectedType(file) {
    const type = (file.type || '').toLowerCase();
    if (type) return type;
    const extension = fileExtension(file);
    if (extension === 'jpg' || extension === 'jpeg') return 'image/jpeg';
    if (extension === 'png') return 'image/png';
    if (extension === 'webp') return 'image/webp';
    if (extension === 'heic') return 'image/heic';
    if (extension === 'heif') return 'image/heif';
    return '';
  }

  function loadLocalImage(file) {
    return new Promise(function (resolve, reject) {
      const url = URL.createObjectURL(file);
      const image = new Image();
      image.onload = function () {
        URL.revokeObjectURL(url);
        resolve(image);
      };
      image.onerror = function () {
        URL.revokeObjectURL(url);
        reject(new Error('No se pudo leer la imagen seleccionada.'));
      };
      image.src = url;
    });
  }

  function canvasToBlob(canvas, quality) {
    return new Promise(function (resolve, reject) {
      canvas.toBlob(function (blob) {
        if (blob) resolve(blob);
        else reject(new Error('Este navegador no pudo comprimir la imagen.'));
      }, 'image/jpeg', quality);
    });
  }

  async function optimizeImage(file) {
    const type = detectedType(file);
    if (HEIC_IMAGE_TYPES.includes(type) || ['heic', 'heif'].includes(fileExtension(file))) {
      throw new Error(
        'HEIC/HEIF todavía no puede procesarse de forma segura. Usa JPG/WebP o configura la cámara en “Más compatible”.'
      );
    }
    if (!SUPPORTED_IMAGE_TYPES.includes(type)) {
      throw new Error('Formato no compatible. Selecciona una imagen JPG, PNG o WebP.');
    }

    const image = await loadLocalImage(file);
    const originalWidth = image.naturalWidth || image.width;
    const originalHeight = image.naturalHeight || image.height;
    if (!originalWidth || !originalHeight) {
      throw new Error('No se pudieron determinar las dimensiones de la imagen.');
    }

    if (
      file.size <= TARGET_IMAGE_SIZE &&
      Math.max(originalWidth, originalHeight) <= MAX_IMAGE_DIMENSION
    ) {
      return { file: file, optimized: false, width: originalWidth, height: originalHeight };
    }

    const scale = Math.min(1, MAX_IMAGE_DIMENSION / Math.max(originalWidth, originalHeight));
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(originalWidth * scale));
    canvas.height = Math.max(1, Math.round(originalHeight * scale));
    const context = canvas.getContext('2d');
    if (!context) throw new Error('Este navegador no permite procesar la imagen.');

    // JPEG has no alpha channel. A white background avoids black transparency.
    context.fillStyle = '#fff';
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(image, 0, 0, canvas.width, canvas.height);

    let quality = INITIAL_JPEG_QUALITY;
    let blob = await canvasToBlob(canvas, quality);
    while (blob.size > TARGET_IMAGE_SIZE && quality > MIN_JPEG_QUALITY) {
      quality = Math.max(MIN_JPEG_QUALITY, quality - 0.07);
      blob = await canvasToBlob(canvas, quality);
    }

    // Highly detailed photos may still exceed the target at minimum quality.
    // Reduce dimensions progressively instead of degrading JPEG quality further.
    let resizeAttempts = 0;
    while (blob.size > TARGET_IMAGE_SIZE && resizeAttempts < 2) {
      const sizeScale = Math.min(0.9, Math.sqrt(TARGET_IMAGE_SIZE / blob.size) * 0.95);
      canvas.width = Math.max(1, Math.round(canvas.width * sizeScale));
      canvas.height = Math.max(1, Math.round(canvas.height * sizeScale));
      context.fillStyle = '#fff';
      context.fillRect(0, 0, canvas.width, canvas.height);
      context.drawImage(image, 0, 0, canvas.width, canvas.height);
      blob = await canvasToBlob(canvas, MIN_JPEG_QUALITY);
      resizeAttempts += 1;
    }
    if (blob.size > TARGET_IMAGE_SIZE) {
      throw new Error('No se pudo reducir la imagen a un tamaño seguro. Prueba con otra fotografía.');
    }

    const baseName = (file.name || 'producto').replace(/\.[^.]+$/, '');
    const optimizedFile = new File([blob], baseName + '.jpg', {
      type: 'image/jpeg',
      lastModified: Date.now(),
    });
    return {
      file: optimizedFile,
      optimized: true,
      width: canvas.width,
      height: canvas.height,
    };
  }

  const imageSlots = [
    ['id_image_file', 'image-preview', 'image-preview-wrap', 'id_remove_image'],
    ['id_secondary_image_file', 'secondary-image-preview', 'secondary-image-preview-wrap', 'id_remove_secondary_image'],
    ['id_tertiary_image_file', 'tertiary-image-preview', 'tertiary-image-preview-wrap', 'id_remove_tertiary_image'],
  ];

  imageSlots.forEach(function (slot) {
    const imageInput = document.getElementById(slot[0]);
    const preview = document.getElementById(slot[1]);
    const previewWrap = document.getElementById(slot[2]);
    const removeImage = document.getElementById(slot[3]);
    const imageSlot = imageInput && imageInput.closest('.product-image-slot');
    const cameraInput = imageSlot && imageSlot.querySelector('.product-camera-input');
    const status = imageSlot && imageSlot.querySelector('.image-processing-status');
    const fieldName = imageSlot && imageSlot.dataset.fieldName;
    let previewUrl = null;
    let selectionVersion = 0;
    if (!imageInput || !preview || !previewWrap) return;

    function setStatus(message, state) {
      if (!status) return;
      status.textContent = message;
      status.classList.toggle('text-danger', state === 'error');
      status.classList.toggle('text-muted', state !== 'error');
    }

    function showPreview(file) {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      if (!file) return;
      previewUrl = URL.createObjectURL(file);
      preview.src = previewUrl;
      previewWrap.classList.remove('d-none');
      if (removeImage) removeImage.checked = false;
    }

    function restoreGalleryField() {
      imageInput.name = fieldName;
      if (cameraInput) cameraInput.removeAttribute('name');
    }

    function assignToDjangoField(file) {
      const transfer = new DataTransfer();
      transfer.items.add(file);
      imageInput.files = transfer.files;
      if (!imageInput.files || imageInput.files.length !== 1) {
        throw new Error('El navegador no permitió preparar la imagen para enviarla.');
      }
      restoreGalleryField();
    }

    async function processSelection(file, sourceInput) {
      const currentVersion = ++selectionVersion;
      const originalSize = file.size;
      let usesCameraFallback = false;
      pendingImageProcesses += 1;
      updateFormBusyState();
      setStatus('Optimizando imagen…', 'progress');

      try {
        const result = await optimizeImage(file);
        if (currentVersion !== selectionVersion) return;
        if (sourceInput === imageInput && result.file === file) {
          restoreGalleryField();
        } else {
          try {
            assignToDjangoField(result.file);
          } catch (assignmentError) {
            if (!result.optimized && sourceInput === cameraInput) {
              imageInput.removeAttribute('name');
              cameraInput.name = fieldName;
              usesCameraFallback = true;
            } else {
              throw assignmentError;
            }
          }
        }
        if (cameraInput && !usesCameraFallback) cameraInput.value = '';
        showPreview(result.file);
        if (result.optimized) {
          setStatus(
            'Optimizada: ' + formatBytes(originalSize) + ' → ' + formatBytes(result.file.size) +
            ' · ' + result.width + '×' + result.height + ' px',
            'ready'
          );
        } else {
          setStatus(
            'Lista sin recompresión: ' + formatBytes(result.file.size) +
            ' · ' + result.width + '×' + result.height + ' px',
            'ready'
          );
        }
      } catch (error) {
        if (currentVersion !== selectionVersion) return;
        imageInput.value = '';
        restoreGalleryField();
        if (sourceInput) sourceInput.value = '';
        setStatus(error.message || 'No se pudo procesar la imagen seleccionada.', 'error');
      } finally {
        pendingImageProcesses = Math.max(0, pendingImageProcesses - 1);
        updateFormBusyState();
      }
    }

    imageInput.addEventListener('change', function () {
      const file = imageInput.files && imageInput.files[0];
      if (!file) return;
      restoreGalleryField();
      if (cameraInput) cameraInput.value = '';
      processSelection(file, imageInput);
    });

    if (cameraInput) {
      cameraInput.addEventListener('change', function () {
        const file = cameraInput.files && cameraInput.files[0];
        if (!file) return;
        processSelection(file, cameraInput);
      });
    }
  });

  if (productForm) {
    productForm.addEventListener('submit', function (event) {
      if (pendingImageProcesses > 0) {
        event.preventDefault();
        return;
      }

      const selectedFiles = new Set();
      productForm.querySelectorAll('input[type="file"]').forEach(function (input) {
        Array.from(input.files || []).forEach(function (file) {
          selectedFiles.add(file);
        });
      });
      const totalImageSize = Array.from(selectedFiles).reduce(function (total, file) {
        return total + file.size;
      }, 0);
      if (totalImageSize > MAX_TOTAL_IMAGE_SIZE) {
        event.preventDefault();
        const firstStatus = productForm.querySelector('.image-processing-status');
        if (firstStatus) {
          firstStatus.textContent = 'Las imágenes seleccionadas superan 4 MB en total. Reduce o reemplaza una de ellas.';
          firstStatus.classList.add('text-danger');
          firstStatus.classList.remove('text-muted');
        }
      }
    });
  }
}());
