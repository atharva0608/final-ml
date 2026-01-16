import React, { useState, useRef, useEffect } from 'react';
import { FiMoreVertical } from 'react-icons/fi';

const Dropdown = ({ trigger, items, align = 'right' }) => {
    const [isOpen, setIsOpen] = useState(false);
    const dropdownRef = useRef(null);

    // Close on click outside
    useEffect(() => {
        const handleClickOutside = (event) => {
            if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
                setIsOpen(false);
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    return (
        <div className="relative inline-block text-left" ref={dropdownRef}>
            <div onClick={() => setIsOpen(!isOpen)} className="cursor-pointer">
                {trigger || (
                    <button className="p-2 rounded-full hover:bg-gray-100 transition-colors text-gray-500">
                        <FiMoreVertical />
                    </button>
                )}
            </div>

            {isOpen && (
                <div
                    className={`
            absolute z-50 mt-2 w-48 rounded-md bg-white shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none 
            ${align === 'right' ? 'right-0' : 'left-0'}
          `}
                >
                    <div className="py-1">
                        {items.map((item, index) => (
                            <button
                                key={index}
                                onClick={(e) => {
                                    e.stopPropagation(); // Prevent closing standard accordions if any
                                    item.onClick();
                                    setIsOpen(false);
                                }}
                                className={`
                  w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 hover:text-gray-900 flex items-center gap-2
                  ${item.className || ''}
                `}
                                disabled={item.disabled}
                            >
                                {item.icon && <span className="text-gray-400">{item.icon}</span>}
                                {item.label}
                            </button>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
};

export default Dropdown;
