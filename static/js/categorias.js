// Highlight de categoría activa al hacer clic
document.querySelectorAll('.cat-card').forEach(card => {
  card.addEventListener('click', function(e) {
    // Solo para preview — en producción Django maneja la navegación
    document.querySelectorAll('.cat-card').forEach(c => c.classList.remove('active'));
    this.classList.add('active');
  });
});
