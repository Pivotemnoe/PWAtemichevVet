const escape = (value) => String(value || '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

export function petAvatar(pet) {
  if (/^data:image\/jpeg;base64,[A-Za-z0-9+/=]+$/.test(pet?.photo_data_url || '')) {
    return `<img class="pet-portrait" src="${pet.photo_data_url}" alt="Фото: ${escape(pet.pet_name)}" width="96" height="96" />`;
  }
  const dog = /собака|dog/i.test(pet?.pet_type || '');
  const shape = dog
    ? '<path d="M19 21c-5-6-12-5-13 1-1 7 1 18 7 20l6-15m26-6c5-6 12-5 13 1 1 7-1 18-7 20l-6-15" fill="#d6a26a"/><path d="M17 25c0-10 30-10 30 0v16c0 18-30 18-30 0Z" fill="#f2d6b5"/><path d="M24 42c1 9 15 9 16 0" fill="#fff6e8"/>'
    : '<path d="m12 28 2-18 15 11h6l15-11 2 18v14c0 20-40 20-40 0Z" fill="#e6edf5"/><path d="m18 24 1-8 8 6m19 2-1-8-8 6" fill="#edb1a3"/><path d="m8 36 13 3M8 45l13-2m35-7-13 3m13 6-13-2" stroke="#7087a0" stroke-width="2" stroke-linecap="round"/>';
  return `<svg class="pet-species-icon" viewBox="0 0 64 64" role="img" aria-label="${dog ? 'Собака' : 'Кошка'}">${shape}<circle cx="24" cy="33" r="2.5" fill="#23445f"/><circle cx="40" cy="33" r="2.5" fill="#23445f"/><path d="m28 41 4 4 4-4Z" fill="#23445f"/><path d="M32 45v4m0 0c-3 4-7 1-7 1m7-1c3 4 7 1 7 1" fill="none" stroke="#23445f" stroke-width="2" stroke-linecap="round"/></svg>`;
}

export async function preparePetPhoto(file) {
  if (!file || file.size > 15 * 1024 * 1024) throw new Error('pet_photo_too_large');
  const source = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error('pet_photo_invalid'));
    reader.readAsDataURL(file);
  });
  const image = await new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error('pet_photo_invalid'));
    img.src = source;
  });
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 512;
  const context = canvas.getContext('2d');
  if (!context || !image.naturalWidth || !image.naturalHeight) throw new Error('pet_photo_invalid');
  const side = Math.min(image.naturalWidth, image.naturalHeight);
  context.fillStyle = '#ffffff'; context.fillRect(0, 0, 512, 512);
  context.drawImage(image, (image.naturalWidth - side) / 2, (image.naturalHeight - side) / 2, side, side, 0, 0, 512, 512);
  return canvas.toDataURL('image/jpeg', 0.86);
}
