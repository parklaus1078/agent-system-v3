import { render, screen } from '@testing-library/react';
import App from './App';

test('renders the product name', () => {
  render(<App />);
  expect(screen.getByText('LLM Dev Control Tower')).toBeInTheDocument();
});
