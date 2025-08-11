// Prevent multiple executions of this script
if (!window.KioskBoardInitialized) {
    window.KioskBoardInitialized = true;
    
    // Initialize KioskBoard configuration (only once)
    KioskBoard.init({
        keysArrayOfObjects: [
            {
                "0": "Q",
                "1": "W",
                "2": "E",
                "3": "R",
                "4": "T",
                "5": "Y",
                "6": "U",
                "7": "I",
                "8": "O",
                "9": "P"
            },
            {
                "0": "A",
                "1": "S",
                "2": "D",
                "3": "F",
                "4": "G",
                "5": "H",
                "6": "J",
                "7": "K",
                "8": "L"
            },
            {
                "0": "Z",
                "1": "X",
                "2": "C",
                "3": "V",
                "4": "B",
                "5": "N",
                "6": "M"
            }
        ],
        language: 'en',
        theme: 'dark',
        autoScroll: true,
        capsLockActive: false,
        keysSpecialCharsArrayOfStrings: [
            '!', '@', '#', '$', '%', '^', '&', '*', '(', ')',
            '-', '_', '=', '+', '[', ']', '{', '}', '|', '\\',
            ':', ';', '"', '\'', '<', '>', ',', '.', '?', '/',
            '`', '~', '€', '£', '¥', '©', '®', '™', '°', '±'
        ],
        keysNumpadArrayOfNumbers: [1, 2, 3, 4, 5, 6, 7, 8, 9, 0],
    });
    
    // Expose function to initialize keyboard on modal
    window.initKeyboardForModal = function() {
        // Find the password input
        const input = document.querySelector('#connect-password');
        if (!input) {
            console.log('Password input not found');
            return;
        }
        
        // Check if KioskBoard was already initialized on this element instance
        // Using a property on the element itself to track initialization
        if (input._kioskBoardInitialized === true) {
            console.log('KioskBoard already initialized on this input');
            return;
        }
        
        // Mark this specific element instance as initialized
        input._kioskBoardInitialized = true;
        
        // Run KioskBoard on this input
        console.log('Initializing KioskBoard on password input');
        KioskBoard.run('#connect-password');
    };
    
    // Also try to initialize on any existing inputs (for non-modal cases)
    // This handles any inputs that might already be in the DOM
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            const existingInputs = document.querySelectorAll('.js-kioskboard-input');
            if (existingInputs.length > 0) {
                KioskBoard.run('.js-kioskboard-input');
            }
        });
    } else {
        // DOM already loaded
        const existingInputs = document.querySelectorAll('.js-kioskboard-input');
        if (existingInputs.length > 0) {
            KioskBoard.run('.js-kioskboard-input');
        }
    }
}