const menuEl = document.getElementById('menuEl');
const sidebarEl = document.getElementById('sidebarEl');
const sidebarOverlayEl = document.getElementById('sidebarOverlayEl');
const mainEl = document.getElementById('mainEl');
const burgerOneEl = document.getElementById('burgerOneEl');
const burgerTwoEl = document.getElementById('burgerTwoEl');
const burgerThreeEl = document.getElementById('burgerThreeEl');

function toggleSidebar() {
  burgerOneEl.classList.toggle('translate-y-[7px]');
  burgerOneEl.classList.toggle('rotate-45');

  burgerTwoEl.classList.toggle('bg-white');

  burgerThreeEl.classList.toggle('translate-y-[-7px]');
  burgerThreeEl.classList.toggle('rotate-[-45deg]');

  sidebarEl.classList.toggle('hidden');
  sidebarOverlayEl.classList.toggle('hidden');
  sidebarOverlayEl.classList.toggle('w-full');
}

menuEl.addEventListener("click", toggleSidebar);
sidebarOverlayEl.addEventListener("click", toggleSidebar);