const canvas = document.getElementById('blueprintCanvas');
const ctx = canvas.getContext('2d');

canvas.width = window.innerWidth * 0.8;
canvas.height = window.innerHeight * 0.8;

let isDrawing = false;
let lastX = 0;
let lastY = 0;

function startDrawing(e) {
    isDrawing = true;
    [lastX, lastY] = [e.offsetX, e.offsetY];
}

function draw(e) {
    if (!isDrawing) return;
    ctx.beginPath();
    ctx.moveTo(lastX, lastY);
    ctx.lineTo(e.offsetX, e.offsetY);
    ctx.strokeStyle = '#0000ff'; // Blue for blueprints
    ctx.lineWidth = 2;
    ctx.stroke();
    [lastX, lastY] = [e.offsetX, e.offsetY];
}

function stopDrawing() {
    isDrawing = false;
}

canvas.addEventListener('mousedown', startDrawing);
canvas.addEventListener('mousemove', draw);
canvas.addEventListener('mouseup', stopDrawing);
canvas.addEventListener('mouseout', stopDrawing);

// Basic text input for idea description (not yet integrated with drawing)
const ideaInput = document.createElement('input');
ideaInput.type = 'text';
ideaInput.placeholder = 'Describe your blueprint idea...';
ideaInput.style.position = 'absolute';
ideaInput.style.top = '10px';
ideaInput.style.left = '50%';
ideaInput.style.transform = 'translateX(-50%)';
ideaInput.style.padding = '10px';
ideaInput.style.border = '1px solid #ccc';
ideaInput.style.borderRadius = '5px';
document.body.appendChild(ideaInput);

// Placeholder for future 3D functionality
console.log("3D Blueprint App initialized. Currently supports 2D drawing. 3D rendering requires more advanced libraries.");

// Resize canvas on window resize
window.addEventListener('resize', () => {
    canvas.width = window.innerWidth * 0.8;
    canvas.height = window.innerHeight * 0.8;
});
