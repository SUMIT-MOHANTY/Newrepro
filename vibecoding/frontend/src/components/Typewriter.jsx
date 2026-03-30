import React, { useState, useEffect } from 'react';

const Typewriter = ({ 
  text, 
  delay = 30, 
  deleteDelay = 20, 
  startDelay = 0, 
  waitBeforeDelete = 3000, 
  onComplete, 
  showCursor = true,
  infinite = false 
}) => {
  const [currentText, setCurrentText] = useState('');
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isStarted, setIsStarted] = useState(false);
  const [isErasing, setIsErasing] = useState(false);

  useEffect(() => {
    // Reset if text changes externally
    setCurrentText('');
    setCurrentIndex(0);
    setIsStarted(false);
    setIsErasing(false);

    if (startDelay > 0) {
      const timer = setTimeout(() => {
        setIsStarted(true);
      }, startDelay);
      return () => clearTimeout(timer);
    } else {
      setIsStarted(true);
    }
  }, [text, startDelay]);

  useEffect(() => {
    if (!isStarted) return;

    if (!isErasing && currentIndex < text.length) {
      // Typing mode
      const timeout = setTimeout(() => {
        setCurrentText(prev => prev + text[currentIndex]);
        setCurrentIndex(prev => prev + 1);
      }, delay);
      return () => clearTimeout(timeout);
    } 
    else if (!isErasing && currentIndex === text.length) {
      // Finished typing, wait then start erasing
      const timeout = setTimeout(() => {
        setIsErasing(true);
      }, waitBeforeDelete);
      return () => clearTimeout(timeout);
    }
    else if (isErasing && currentIndex > 0) {
      // Erasing mode
      const timeout = setTimeout(() => {
        setCurrentText(prev => prev.slice(0, -1));
        setCurrentIndex(prev => prev - 1);
      }, deleteDelay);
      return () => clearTimeout(timeout);
    }
    else if (isErasing && currentIndex === 0) {
      // Finished erasing cycle
      if (onComplete) {
        onComplete();
      }
    }
  }, [currentIndex, delay, deleteDelay, text, onComplete, isStarted, isErasing, waitBeforeDelete]);

  return (
    <span>
      {currentText}
      {showCursor && isStarted && (
        <span className="typewriter-cursor" />
      )}
    </span>
  );
};

export default Typewriter;
