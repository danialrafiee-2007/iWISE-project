// Browser page translation (Chrome, Edge) replaces text nodes with its own <font> elements behind React's back.
// React then asks the DOM to remove or insert next to a node that is no longer there, which throws and blanks the
// page. This guard (the workaround from facebook/react#11538) turns those calls into safe ones: a node that is not
// a child is not removed, and an insert before a vanished reference node is appended instead of thrown away.

export function guardAgainstTranslation() {
  if (typeof Node !== "function" || !Node.prototype) return;
  const removeChild = Node.prototype.removeChild;
  Node.prototype.removeChild = function <T extends Node>(this: Node, child: T): T {
    if (child.parentNode !== this) return child;
    return removeChild.call(this, child) as T;
  };
  const insertBefore = Node.prototype.insertBefore;
  Node.prototype.insertBefore = function <T extends Node>(this: Node, node: T, reference: Node | null): T {
    if (reference && reference.parentNode !== this) return insertBefore.call(this, node, null) as T;
    return insertBefore.call(this, node, reference) as T;
  };
}
